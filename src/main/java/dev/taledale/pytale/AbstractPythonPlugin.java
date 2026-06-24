package dev.taledale.pytale;

import com.hypixel.hytale.event.IAsyncEvent;
import com.hypixel.hytale.event.IEvent;
import com.hypixel.hytale.server.core.plugin.JavaPlugin;
import com.hypixel.hytale.server.core.plugin.JavaPluginInit;
import com.hypixel.hytale.server.core.universe.Universe;
import com.hypixel.hytale.server.core.universe.world.World;
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

            if (hasAsyncEventHandlers()) {
                asyncContext = new AsyncPythonContext(
                        this,
                        getLogger().getSubLogger("AsyncContext"));
                asyncContext.init();
            }

            readAndRegisterEventHandlers();
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

    public Engine getPythonEngine() {
        return pythonEngine;
    }

    public Context getGeneralContext() {
        return generalContext != null ? generalContext.getContext() : null;
    }
}
