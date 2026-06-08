package dev.taledale.pytale;

import com.hypixel.hytale.server.core.plugin.JavaPlugin;
import com.hypixel.hytale.server.core.plugin.JavaPluginInit;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.PolyglotException;

import javax.annotation.Nonnull;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public abstract class AbstractPythonPlugin extends JavaPlugin {
    private final AtomicReference<Context> generalContext = new AtomicReference<>();
    private PluginSchedulerContext schedulerContext;
    private SingleThreadPythonRuntime runtime;
    private WorldContextManager worldContextManager;

    public AbstractPythonPlugin(@Nonnull JavaPluginInit init) {
        super(init);
    }

    @Override
    protected void setup() {
        try {
            String pythonCode = loadPythonCode();
            runtime = new SingleThreadPythonRuntime();
            schedulerContext = new PluginSchedulerContext(this);
            worldContextManager = new WorldContextManager(this);

            initializeGeneralContext(pythonCode);
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

    private void initializeGeneralContext(String code) {
        CountDownLatch latch = new CountDownLatch(1);

        runtime.submit(() -> {
            ClassLoader previousCl = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                Context ctx = PythonContextFactory.newContext();
                generalContext.set(ctx);
                getLogger().atInfo().log("General Python context initialized");

                ctx.eval("python", code);
                getLogger().atInfo().log("Plugin code executed");
            } catch (PolyglotException e) {
                getLogger().atWarning().log("Python error during initialization: %s", e.getMessage());
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

    private void initializeSchedulerContext() {
        schedulerContext.initialize();
    }

    public Context getGeneralContext() {
        return generalContext.get();
    }

    public PluginSchedulerContext getSchedulerContext() {
        return schedulerContext;
    }

    protected String loadPythonCode() throws Exception {
        InputStream is = getClass().getResourceAsStream("/python/__init__.py");
        if (is == null) {
            throw new Exception("python/__init__.py not found in plugin resources");
        }
        return new String(is.readAllBytes(), StandardCharsets.UTF_8);
    }
}
