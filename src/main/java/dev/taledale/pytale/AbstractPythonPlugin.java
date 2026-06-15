package dev.taledale.pytale;

import com.hypixel.hytale.event.IEvent;
import com.hypixel.hytale.server.core.plugin.JavaPlugin;
import com.hypixel.hytale.server.core.plugin.JavaPluginInit;
import com.hypixel.hytale.server.core.universe.Universe;
import com.hypixel.hytale.server.core.universe.world.World;
import dev.taledale.pytale.context.PythonContext;
import dev.taledale.pytale.context.world.WorldContextManager;
import dev.taledale.pytale.context.world.WorldPythonContext;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Engine;
import org.graalvm.polyglot.Value;

import javax.annotation.Nonnull;
import java.util.List;
import java.util.function.Consumer;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public abstract class AbstractPythonPlugin extends JavaPlugin {
    private final AtomicReference<List<String>> wheelPaths = new AtomicReference<>();
    private Engine pythonEngine;
    private ExecutorService generalExecutor;
    private PythonContext generalContext;
    private WorldContextManager worldContextManager;

    public AbstractPythonPlugin(@Nonnull JavaPluginInit init) {
        super(init);
    }

    @Override
    protected void setup() {
        try {
            pythonEngine = Engine.newBuilder("python")
                    .option("engine.WarnInterpreterOnly", "false")
                    .build();

            generalExecutor = Executors.newSingleThreadExecutor(r -> {
                Thread t = new Thread(r, "PyTale-" + getManifest().getName() + "-General");
                t.setDaemon(true);
                return t;
            });

            worldContextManager = new WorldContextManager(this);

            List<String> wheels = extractWheels(getPluginJarPath());
            getLogger().atInfo().log("Found %d wheel(s)", wheels.size());

            generalContext = new PythonContext(
                    this,
                    getLogger().getSubLogger("GeneralContext"),
                    ExecutionContext.GENERAL);
            submitToGeneral(generalContext::init, true);

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

        if (generalContext != null) {
            submitToGeneral(generalContext::close, true);

            generalExecutor.shutdown();
            try {
                if (!generalExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                    generalExecutor.shutdownNow();
                }
            } catch (InterruptedException e) {
                generalExecutor.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }

        if (pythonEngine != null) {
            pythonEngine.close();
        }
    }

    private void executeLifecycleListeners(String event) {
        if (generalContext == null)
            return;
        Context ctx = generalContext.getContext();
        if (ctx == null)
            return;

        submitToGeneral(() -> {
            ctx.enter();
            try {
                Value bindings = ctx.getBindings("python");
                bindings.putMember("__event", event);
                ctx.eval("python",
                        "from pytale.plugin._lifecycle import _execute_listeners\n" +
                                "_execute_listeners(__event)");
            } catch (Exception e) {
                getLogger().atWarning().log("Error executing %s listeners: %s", event, e.getMessage());
            } finally {
                ctx.leave();
            }
        }, true);
    }

    @SuppressWarnings({ "unchecked", "rawtypes", "null" })
    private void readAndRegisterEventHandlers() {
        if (generalContext == null)
            return;
        Context ctx = generalContext.getContext();
        if (ctx == null)
            return;

        submitToGeneral(() -> {
            ctx.enter();
            try {
                ctx.eval("python",
                        "import pytale.events._registry as __reg\n" +
                                "__handlers = __reg._handlers");
                Value handlers = ctx.getBindings("python").getMember("__handlers");
                int size = (int) handlers.getArraySize();
                for (int i = 0; i < size; i++) {
                    int index = i;
                    Value handler = handlers.getArrayElement(i);
                    Class<? extends IEvent<?>> eventClass = (Class<? extends IEvent<?>>) handler.getMember("java_class")
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
            } catch (Exception e) {
                getLogger().atWarning().log("Error reading event handlers: %s", e.getMessage());
            } finally {
                ctx.leave();
            }
        }, true);
    }

    private void dispatchToCurrentThread(int index, IEvent<?> event) {
        World world = Universe.get().getWorlds().values().stream()
                .filter(World::isInThread)
                .findFirst()
                .orElse(null);
        if (world == null) {
            getLogger().atWarning().log("No world for current thread, skipping event handler %d", index);
            return;
        }
        WorldPythonContext context = worldContextManager.getContext(world);
        if (context == null) {
            getLogger().atWarning().log("No context for world %s, skipping event handler %d", world.getName(),
                    index);
            return;
        }
        context.invokeEventHandler(index, event);
    }

    public void submitToGeneral(Runnable task) {
        submitToGeneral(task, false);
    }

    private void submitToGeneral(Runnable task, boolean await) {
        if (generalExecutor == null)
            return;

        CountDownLatch latch = await ? new CountDownLatch(1) : null;
        generalExecutor.submit(() -> {
            ClassLoader prev = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                task.run();
            } finally {
                Thread.currentThread().setContextClassLoader(prev);
                if (latch != null)
                    latch.countDown();
            }
        });

        if (latch != null) {
            try {
                if (!latch.await(5, TimeUnit.SECONDS)) {
                    getLogger().atWarning().log("Task on general executor timed out");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }

    public Engine getPythonEngine() {
        return pythonEngine;
    }

    public Context getGeneralContext() {
        return generalContext != null ? generalContext.getContext() : null;
    }

    public List<String> getWheelPaths() {
        List<String> paths = wheelPaths.get();
        return paths != null ? paths : new java.util.ArrayList<>();
    }

    private java.nio.file.Path getPluginJarPath() throws Exception {
        java.nio.file.Path pluginFile = getFile();
        if (pluginFile == null || !java.nio.file.Files.exists(pluginFile)) {
            throw new Exception("Cannot determine plugin location");
        }
        return pluginFile;
    }

    private List<String> extractWheels(java.nio.file.Path pluginJarPath) throws Exception {
        List<String> wheelPathsList = new java.util.ArrayList<>();
        java.nio.file.Path tempDir = java.nio.file.Files.createTempDirectory(
                "pytale-wheels-");

        try (java.util.zip.ZipFile zf = new java.util.zip.ZipFile(pluginJarPath.toFile())) {
            zf.stream()
                    .filter(entry -> entry.getName().endsWith(".whl") && !entry.isDirectory())
                    .forEach(entry -> {
                        try {
                            java.nio.file.Path wheelDest = tempDir.resolve(entry.getName());
                            try (java.io.InputStream is = zf.getInputStream(entry)) {
                                java.nio.file.Files.copy(is, wheelDest,
                                        java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                            }
                            wheelPathsList.add(wheelDest.toAbsolutePath().toString());
                            getLogger().atInfo().log("Extracted wheel: %s", wheelDest);
                        } catch (Exception e) {
                            getLogger().atWarning().log("Failed to extract wheel %s: %s",
                                    entry.getName(), e.getMessage());
                        }
                    });
        }

        wheelPaths.set(wheelPathsList);
        return wheelPathsList;
    }
}
