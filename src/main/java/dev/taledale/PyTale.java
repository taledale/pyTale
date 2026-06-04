package dev.taledale;

import com.hypixel.hytale.server.core.plugin.JavaPlugin;
import com.hypixel.hytale.server.core.plugin.JavaPluginInit;

import javax.annotation.Nonnull;

public class PyTale extends JavaPlugin {
    private static PyTale instance;
    private SingleThreadPythonRuntime runtime;
    private PluginLoader pluginLoader;
    private WorldContextManager worldContextManager;
    private SchedulerPythonContext schedulerContext;

    public PyTale(@Nonnull JavaPluginInit init) {
        super(init);
    }

    public static PyTale get() {
        return instance;
    }

    @Override
    protected void setup() {
        instance = this;
        getLogger().atInfo().log("PyTale setup started");

        runtime = new SingleThreadPythonRuntime();
        pluginLoader = new PluginLoader(runtime);
        pluginLoader.loadAll();

        schedulerContext = new SchedulerPythonContext(getTaskRegistry());

        worldContextManager = new WorldContextManager(getEventRegistry());
        worldContextManager.start();

        getLogger().atInfo().log("PyTale setup completed");
    }

    @Override
    protected void shutdown() {
        getLogger().atInfo().log("PyTale shutdown started");
        if (worldContextManager != null) {
            worldContextManager.shutdown();
        }
        if (schedulerContext != null) {
            schedulerContext.close();
        }
        if (pluginLoader != null) {
            pluginLoader.shutdown();
        }
        getLogger().atInfo().log("PyTale shutdown completed");
    }

    public WorldContextManager getWorldContextManager() {
        return worldContextManager;
    }

    public SchedulerPythonContext getSchedulerContext() {
        return schedulerContext;
    }
}
