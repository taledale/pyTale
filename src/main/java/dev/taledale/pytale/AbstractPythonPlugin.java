package dev.taledale.pytale;

import com.hypixel.hytale.event.IAsyncEvent;
import com.hypixel.hytale.event.IEvent;
import com.hypixel.hytale.server.core.command.system.AbstractCommand;
import com.hypixel.hytale.server.core.command.system.arguments.system.Argument;
import com.hypixel.hytale.server.core.command.system.arguments.types.ArgTypes;
import com.hypixel.hytale.server.core.command.system.arguments.types.ArgumentType;
import com.hypixel.hytale.server.core.plugin.JavaPlugin;
import com.hypixel.hytale.server.core.plugin.JavaPluginInit;
import com.hypixel.hytale.server.core.universe.Universe;
import com.hypixel.hytale.server.core.universe.world.World;
import dev.taledale.pytale.command.*;
import dev.taledale.pytale.context.AsyncPythonContext;
import dev.taledale.pytale.context.ExecutionContext;
import dev.taledale.pytale.context.PythonContext;
import dev.taledale.pytale.context.world.WorldContextManager;
import dev.taledale.pytale.context.world.WorldPythonContext;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Engine;
import org.graalvm.polyglot.Value;

import javax.annotation.Nonnull;
import java.net.URL;
import java.net.URLClassLoader;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;
import java.util.function.Function;

public abstract class AbstractPythonPlugin extends JavaPlugin {
    private Engine pythonEngine;
    private PythonContext generalContext;
    private AsyncPythonContext asyncContext;
    private WorldContextManager worldContextManager;
    private URLClassLoader resourceClassLoader;
    private Class<?> resourceAnchorClass;

    public AbstractPythonPlugin(@Nonnull JavaPluginInit init) {
        super(init);
    }

    /**
     * Builds a class loader whose resources are the plugin jar, used by the GraalPy
     * {@link org.graalvm.python.embedding.VirtualFileSystem} to locate the embedded venv.
     *
     * <p>We load an anchor class child-first from the plugin jar itself ({@link #getFile()}),
     * so its class loader's {@code getResources} resolves the VFS metadata regardless of how
     * the framework is deployed.
     */
    private void initResourceAnchor() throws Exception {
        URL jarUrl = getFile().toUri().toURL();
        resourceClassLoader = new URLClassLoader(new URL[] { jarUrl }, getClass().getClassLoader()) {
            @Override
            protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
                synchronized (getClassLoadingLock(name)) {
                    Class<?> c = findLoadedClass(name);
                    if (c == null) {
                        try {
                            c = findClass(name); // prefer the plugin jar copy
                        } catch (ClassNotFoundException e) {
                            return super.loadClass(name, resolve); // fall back to parent (framework)
                        }
                    }
                    if (resolve) {
                        resolveClass(c);
                    }
                    return c;
                }
            }
        };
        resourceAnchorClass = resourceClassLoader.loadClass(getClass().getName());
    }

    /** Class whose class loader resolves this plugin's embedded VFS resources. */
    public Class<?> getResourceAnchorClass() {
        return resourceAnchorClass;
    }

    @Override
    protected void setup() {
        try {
            pythonEngine = Engine.newBuilder("python")
                    .option("engine.WarnInterpreterOnly", "false")
                    .build();

            initResourceAnchor();

            worldContextManager = new WorldContextManager(this);

            generalContext = new PythonContext(
                    this,
                    getLogger().getSubLogger("GeneralContext"),
                    ExecutionContext.GENERAL);
            generalContext.init();

            if (hasAsyncEventHandlers() || hasAsyncCommands()) {
                asyncContext = new AsyncPythonContext(
                        this,
                        getLogger().getSubLogger("AsyncContext"));
                asyncContext.init();
            }

            readAndRegisterEventHandlers();
            readAndRegisterCommands();
            executeLifecycleListeners("setup");
            worldContextManager.start();
        } catch (Exception e) {
            getLogger().atSevere().log("Failed to load Python plugin: %s", e.getMessage());
        }
    }

    @Override
    protected void start() {
        executeLifecycleListeners("start");
    }

    @Override
    protected void shutdown() {
        executeLifecycleListeners("shutdown");

        if (worldContextManager != null) {
            worldContextManager.shutdown();
        }

        if (asyncContext != null) {
            asyncContext.close(true);
        }

        if (generalContext != null) {
            generalContext.close(true);
        }

        if (pythonEngine != null) {
            pythonEngine.close();
        }

        // Closed last: the VFS reads resources lazily through this loader during the contexts'
        // lifetime.
        if (resourceClassLoader != null) {
            try {
                resourceClassLoader.close();
            } catch (Exception e) {
                getLogger().atWarning().log("Error closing resource class loader: %s", e.getMessage());
            }
        }
    }

    private void executeLifecycleListeners(String event) {
        if (generalContext == null)
            return;
        Context ctx = generalContext.getContext();
        if (ctx == null)
            return;

        generalContext.withContext(() -> {
            try {
                ctx.getBindings("python").putMember("__event", event);
                ctx.eval("python",
                        "from pytale.plugin._lifecycle import _execute_listeners\n" +
                                "_execute_listeners(__event)");
            } catch (Exception e) {
                getLogger().atWarning().log("Error executing %s listeners: %s", event, e.getMessage());
            }
        });
    }

    private boolean hasAsyncEventHandlers() {
        if (generalContext == null)
            return false;
        Context ctx = generalContext.getContext();
        if (ctx == null)
            return false;

        AtomicBoolean result = new AtomicBoolean(false);
        generalContext.withContext(() -> {
            try {
                ctx.eval("python",
                        "import pytale.events._registry as __reg\n" +
                                "__async_handlers = __reg._async_handlers");
                result.set(ctx.getBindings("python").getMember("__async_handlers").getArraySize() > 0);
            } catch (Exception e) {
                getLogger().atWarning().log("Error checking async handlers: %s", e.getMessage());
            }
        });
        return result.get();
    }

    @SuppressWarnings({ "unchecked", "rawtypes", "null" })
    private void readAndRegisterEventHandlers() {
        if (generalContext == null)
            return;
        Context ctx = generalContext.getContext();
        if (ctx == null)
            return;

        generalContext.withContext(() -> {
            try {
                ctx.eval("python",
                        "import pytale.events._registry as __reg\n" +
                                "__handlers = __reg._handlers");
                Value handlers = ctx.getBindings("python").getMember("__handlers");
                int size = (int) handlers.getArraySize();
                for (int i = 0; i < size; i++) {
                    int index = i;
                    Value handler = handlers.getArrayElement(i);
                    Class<? extends IEvent<?>> eventClass = handler.getMember("java_class")
                            .asHostObject();
                    short priority = (short) handler.getMember("priority").asInt();
                    Value keyValue = handler.getMember("key");
                    Consumer<IEvent<?>> listener = event -> dispatchToCurrentThread(index, event);
                    if (keyValue.isNull()) {
                        getEventRegistry().registerGlobal(priority, (Class) eventClass, (Consumer) listener);
                    } else {
                        Object key = keyValue.asHostObject();
                        getEventRegistry().register(priority, (Class) eventClass, key, (Consumer) listener);
                    }
                    getLogger().atInfo().log("Registered event handler %d for %s", index, eventClass.getSimpleName());
                }

                ctx.eval("python",
                        "__async_handlers = __reg._async_handlers");
                Value asyncHandlers = ctx.getBindings("python").getMember("__async_handlers");
                int asyncSize = (int) asyncHandlers.getArraySize();
                for (int i = 0; i < asyncSize; i++) {
                    int index = i;
                    Value handler = asyncHandlers.getArrayElement(i);
                    Class<? extends IAsyncEvent<?>> eventClass = handler
                            .getMember("java_class").asHostObject();
                    short priority = (short) handler.getMember("priority").asInt();
                    Value keyValue = handler.getMember("key");
                    Function<CompletableFuture<IAsyncEvent<?>>, CompletableFuture<IAsyncEvent<?>>> listener = upstream -> upstream
                            .thenCompose(event -> {
                                CompletableFuture<IAsyncEvent<?>> future = new CompletableFuture<>();
                                asyncContext.enqueue(index, event, future);
                                return future;
                            });
                    if (keyValue.isNull()) {
                        getEventRegistry().registerAsyncGlobal(priority, (Class) eventClass, (Function) listener);
                    } else {
                        Object key = keyValue.asHostObject();
                        getEventRegistry().registerAsync(priority, (Class) eventClass, key, (Function) listener);
                    }
                    getLogger().atInfo().log("Registered async event handler %d for %s", index,
                            eventClass.getSimpleName());
                }
            } catch (Exception e) {
                getLogger().atWarning().log("Error reading event handlers: %s", e.getMessage());
            }
        });
    }

    @SuppressWarnings("null")
    private void dispatchToCurrentThread(int index, IEvent<?> event) {
        World world = Universe.get().getWorlds().values().stream()
                .filter(World::isInThread)
                .findFirst()
                .orElse(null);
        if (world != null) {
            WorldPythonContext context = worldContextManager.getContext(world);
            if (context == null) {
                getLogger().atWarning().log("No context for world %s, skipping event handler %d", world.getName(),
                        index);
                return;
            }
            context.invokeEventHandler(index, event);
            return;
        }
        if (generalContext == null) {
            getLogger().atWarning().log("General context not initialized, skipping event handler %d", index);
            return;
        }
        generalContext.invokeEventHandler(index, event);
    }

    private boolean hasAsyncCommands() {
        if (generalContext == null) return false;
        Context ctx = generalContext.getContext();
        if (ctx == null) return false;

        AtomicBoolean result = new AtomicBoolean(false);
        generalContext.withContext(() -> {
            try {
                ctx.eval("python",
                        "import pytale.commands._registry as __cmd_reg\n" +
                                "__cmd_async_handlers = __cmd_reg._async_handlers");
                result.set(ctx.getBindings("python").getMember("__cmd_async_handlers").getArraySize() > 0);
            } catch (Exception e) {
                getLogger().atWarning().log("Error checking async commands: %s", e.getMessage());
            }
        });
        return result.get();
    }

    private static ArgumentType<?> resolveArgType(String argTypeName) {
        return switch (argTypeName) {
            case "BOOLEAN" -> ArgTypes.BOOLEAN;
            case "INTEGER" -> ArgTypes.INTEGER;
            case "FLOAT" -> ArgTypes.FLOAT;
            case "DOUBLE" -> ArgTypes.DOUBLE;
            case "STRING" -> ArgTypes.STRING;
            case "GREEDY_STRING" -> ArgTypes.GREEDY_STRING;
            case "UUID" -> ArgTypes.UUID;
            case "PLAYER_REF" -> ArgTypes.PLAYER_REF;
            case "WORLD" -> ArgTypes.WORLD;
            case "GAME_MODE" -> ArgTypes.GAME_MODE;
            default -> throw new IllegalArgumentException("Unknown arg type: " + argTypeName);
        };
    }

    @SuppressWarnings("null")
    private void buildArguments(AbstractCommand command, Value args, Map<String, Argument<?, ?>> argMap) {
        long size = args.getArraySize();
        for (int i = 0; i < size; i++) {
            Value arg = args.getArrayElement(i);
            String argName = arg.getMember("name").asString();
            Value descValue = arg.getMember("description");
            String argDesc = descValue.isNull() || !descValue.isString() ? "" : descValue.asString();

            // FlagArg has no arg_type
            if (!arg.hasMember("arg_type") || arg.getMember("arg_type").isNull()) {
                argMap.put(argName, command.withFlagArg(argName, argDesc));
                continue;
            }

            String typeName = arg.getMember("arg_type").getMember("value").asString();
            ArgumentType<?> argType = resolveArgType(typeName);

            boolean required = arg.getMember("required").asBoolean();
            if (required) {
                argMap.put(argName, command.withRequiredArg(argName, argDesc, argType));
            } else {
                argMap.put(argName, command.withOptionalArg(argName, argDesc, argType));
            }
        }
    }

    @SuppressWarnings("null")
    private AbstractCommand createCommandFromHandler(Value handler) {
        String name = handler.getMember("name").asString();
        String description = handler.getMember("description").asString();
        String commandType = handler.getMember("command_type").getMember("value").asString();
        int handlerIndex = handler.getMember("index").asInt();
        Value argsValue = handler.getMember("args");

        // Create with a mutable map; buildArguments fills it by calling withRequiredArg/etc.
        // on the same command instance, so args are registered on the correct object.
        Map<String, Argument<?, ?>> argMap = new LinkedHashMap<>();
        AbstractCommand command = switch (commandType) {
            case "DEFAULT" -> new PythonDefaultCommand(
                    name, description, handlerIndex, argMap, asyncContext);
            case "WORLD" -> new PythonWorldCommand(
                    name, description, handlerIndex, argMap, worldContextManager);
            case "ASYNC_WORLD" -> new PythonAsyncWorldCommand(
                    name, description, handlerIndex, argMap, asyncContext);
            case "PLAYER" -> new PythonPlayerCommand(
                    name, description, handlerIndex, argMap, worldContextManager);
            case "ASYNC_PLAYER" -> new PythonAsyncPlayerCommand(
                    name, description, handlerIndex, argMap, asyncContext);
            default -> throw new IllegalArgumentException("Unknown command type: " + commandType);
        };
        buildArguments(command, argsValue, argMap);

        // Permission
        Value permValue = handler.getMember("permission");
        if (!permValue.isNull()) {
            command.requirePermission(permValue.asString());
        }

        // Aliases
        Value aliases = handler.getMember("aliases");
        if (aliases.hasArrayElements() && aliases.getArraySize() > 0) {
            String[] aliasArray = new String[(int) aliases.getArraySize()];
            for (int i = 0; i < aliasArray.length; i++) {
                aliasArray[i] = aliases.getArrayElement(i).asString();
            }
            command.addAliases(aliasArray);
        }

        return command;
    }

    @SuppressWarnings("null")
    private AbstractCommand buildCollection(Value collection) {
        String name = collection.getMember("name").asString();
        String description = collection.getMember("description").asString();
        PythonCommandCollection cmd = new PythonCommandCollection(name, description);

        Value permValue = collection.getMember("permission");
        if (!permValue.isNull()) {
            cmd.requirePermission(permValue.asString());
        }

        Value aliases = collection.getMember("aliases");
        if (aliases.hasArrayElements() && aliases.getArraySize() > 0) {
            String[] aliasArray = new String[(int) aliases.getArraySize()];
            for (int i = 0; i < aliasArray.length; i++) {
                aliasArray[i] = aliases.getArrayElement(i).asString();
            }
            cmd.addAliases(aliasArray);
        }

        // Sub-commands
        Value subCommands = collection.getMember("sub_commands");
        for (int i = 0; i < subCommands.getArraySize(); i++) {
            AbstractCommand subCmd = createCommandFromHandler(subCommands.getArrayElement(i));
            cmd.addSubCommand(subCmd);
        }

        // Nested collections
        Value subCollections = collection.getMember("sub_collections");
        for (int i = 0; i < subCollections.getArraySize(); i++) {
            AbstractCommand nested = buildCollection(subCollections.getArrayElement(i));
            cmd.addSubCommand(nested);
        }

        return cmd;
    }

    @SuppressWarnings("null")
    private void readAndRegisterCommands() {
        if (generalContext == null) return;
        Context ctx = generalContext.getContext();
        if (ctx == null) return;

        generalContext.withContext(() -> {
            try {
                ctx.eval("python",
                        "import pytale.commands._registry as __cmd_reg\n" +
                                "__cmd_commands = __cmd_reg._commands\n" +
                                "__cmd_collections = __cmd_reg._collections");

                // Standalone commands
                Value commands = ctx.getBindings("python").getMember("__cmd_commands");
                for (int i = 0; i < commands.getArraySize(); i++) {
                    Value handler = commands.getArrayElement(i);
                    AbstractCommand command = createCommandFromHandler(handler);
                    getCommandRegistry().registerCommand(command);
                    getLogger().atInfo().log("Registered command /%s", command.getName());
                }

                // Collections
                Value collections = ctx.getBindings("python").getMember("__cmd_collections");
                for (int i = 0; i < collections.getArraySize(); i++) {
                    AbstractCommand collection = buildCollection(collections.getArrayElement(i));
                    getCommandRegistry().registerCommand(collection);
                    getLogger().atInfo().log("Registered command collection /%s", collection.getName());
                }
            } catch (Exception e) {
                getLogger().atWarning().log("Error reading commands: %s", e.getMessage());
            }
        });
    }

    public Engine getPythonEngine() {
        return pythonEngine;
    }

    public Context getGeneralContext() {
        return generalContext != null ? generalContext.getContext() : null;
    }

    public WorldContextManager getWorldContextManager() {
        return worldContextManager;
    }
}
