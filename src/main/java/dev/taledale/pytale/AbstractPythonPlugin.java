package dev.taledale.pytale;

import com.hypixel.hytale.server.core.plugin.JavaPlugin;
import com.hypixel.hytale.server.core.plugin.JavaPluginInit;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.PolyglotException;

import javax.annotation.Nonnull;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public abstract class AbstractPythonPlugin extends JavaPlugin {
    private final AtomicReference<Context> generalContext = new AtomicReference<>();
    private final AtomicReference<java.util.List<String>> wheelPaths = new AtomicReference<>();
    private PluginSchedulerContext schedulerContext;
    private SingleThreadPythonRuntime runtime;
    private WorldContextManager worldContextManager;

    public AbstractPythonPlugin(@Nonnull JavaPluginInit init) {
        super(init);
    }

    @Override
    protected void setup() {
        try {
            runtime = new SingleThreadPythonRuntime();
            schedulerContext = new PluginSchedulerContext(this);
            worldContextManager = new WorldContextManager(this);

            initializeGeneralContext();
            initializeSchedulerContext();
            worldContextManager.start();
        } catch (Exception e) {
            getLogger().atSevere().log("Failed to load Python plugin: %s", e.getMessage());
        }
    }

    @Override
    protected void shutdown() {
        Context ctx = generalContext.get();
        if (ctx != null) {
            try {
                ctx.close();
                getLogger().atInfo().log("General Python context closed");
            } catch (Exception e) {
                getLogger().atSevere().log("Error closing context: %s", e.getMessage());
            }
        }
        if (schedulerContext != null) {
            schedulerContext.close();
        }
        if (worldContextManager != null) {
            worldContextManager.shutdown();
        }
    }

    private void initializeGeneralContext() {
        CountDownLatch latch = new CountDownLatch(1);

        runtime.submit(() -> {
            ClassLoader previousCl = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                Context ctx = PythonContextFactory.newContext();
                generalContext.set(ctx);
                getLogger().atInfo().log("General Python context initialized");

                java.nio.file.Path pluginJarPath = getPluginJarPath();
                String moduleName = getPythonModuleName();
                java.util.List<String> wheelPathsList = extractWheels(pluginJarPath);

                getLogger().atInfo().log("Found %d wheel(s)", wheelPathsList.size());

                StringBuilder setupCode = new StringBuilder();
                setupCode.append("import sys\n");
                for (String wheelPath : wheelPathsList) {
                    setupCode.append(String.format("sys.path.insert(0, '%s')\n", wheelPath));
                }

                ctx.eval("python", setupCode.toString());

                initializePytale(ctx, ExecutionContext.GENERAL);

                setupCode = new StringBuilder();
                setupCode.append(String.format("import %s", moduleName));
                ctx.eval("python", setupCode.toString());
            } catch (PolyglotException e) {
                getLogger().atWarning().log("Python error during initialization: %s", e.getMessage());
            } catch (Exception e) {
                getLogger().atWarning().log("Error executing plugin: %s", e.getMessage());
            } finally {
                Thread.currentThread().setContextClassLoader(previousCl);
                latch.countDown();
            }
        });

        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                getLogger().atWarning().log("General context initialization timed out");
            }
        } catch (InterruptedException e) {
            getLogger().atWarning().log("General context initialization interrupted");
            Thread.currentThread().interrupt();
        }
    }

    protected String loadPythonCode() throws Exception {
        String moduleName = getPythonModuleName();
        String entryPath = "python/" + moduleName + "/__init__.py";

        java.nio.file.Path location = getPluginJarPath();

        try (java.util.zip.ZipFile zf = new java.util.zip.ZipFile(location.toFile())) {
            java.util.zip.ZipEntry entry = zf.getEntry(entryPath);
            if (entry == null) {
                throw new Exception("Python code not found in plugin: " + entryPath);
            }
            try (java.io.InputStream is = zf.getInputStream(entry)) {
                return new String(is.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
            }
        }
    }

    private java.nio.file.Path getPluginJarPath() throws Exception {
        java.nio.file.Path pluginFile = getFile();
        if (pluginFile == null || !java.nio.file.Files.exists(pluginFile)) {
            throw new Exception("Cannot determine plugin location");
        }
        return pluginFile;
    }

    private String getPythonModuleName() throws Exception {
        String name = getManifest().getName();
        return name.replace("-", "_");
    }

    protected void initializePytale(Context ctx, ExecutionContext executionContext) {
        org.graalvm.polyglot.Value bindings = ctx.getBindings("python");
        bindings.putMember("__identifier", getIdentifier());
        bindings.putMember("__manifest", getManifest());
        bindings.putMember("__data_directory", getDataDirectory());
        bindings.putMember("__context", executionContext.getValue());
        ctx.eval("python",
                "import pytale.plugin._plugin\n" +
                        "pytale.plugin._plugin._init_plugin" +
                        "(__identifier, __manifest, __data_directory, __context)");
    }

    private void initializeSchedulerContext() {
        schedulerContext.initialize();
    }

    public Context getGeneralContext() {
        return generalContext.get();
    }

    public PluginSchedulerContext getSchedulerContext() {
        return schedulerContext;
    }

    public java.util.List<String> getWheelPaths() {
        java.util.List<String> paths = wheelPaths.get();
        return paths != null ? paths : new java.util.ArrayList<>();
    }

    private java.util.List<String> extractWheels(java.nio.file.Path pluginJarPath) throws Exception {
        java.util.List<String> wheelPathsList = new java.util.ArrayList<>();
        java.nio.file.Path tempDir = java.nio.file.Files.createTempDirectory("pytale-wheels-");

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
                            getLogger().atWarning().log("Failed to extract wheel %s: %s", entry.getName(),
                                    e.getMessage());
                        }
                    });
        }

        wheelPaths.set(wheelPathsList);
        return wheelPathsList;
    }
}
