package dev.taledale.pytale.context;

import com.hypixel.hytale.event.IEvent;
import com.hypixel.hytale.logger.HytaleLogger;
import dev.taledale.pytale.AbstractPythonPlugin;
import dev.taledale.pytale.ExecutionContext;
import dev.taledale.pytale.PyTale;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.HostAccess;
import org.graalvm.polyglot.PolyglotException;
import org.graalvm.polyglot.Value;

import java.util.List;
import java.util.concurrent.locks.ReentrantLock;

public class PythonContext {
    protected final AbstractPythonPlugin plugin;
    protected final HytaleLogger logger;
    protected final ExecutionContext executionContext;
    protected Context context;
    private final ReentrantLock lock = new ReentrantLock();

    public PythonContext(
            AbstractPythonPlugin plugin,
            HytaleLogger logger,
            ExecutionContext executionContext) {
        this.plugin = plugin;
        this.logger = logger;
        this.executionContext = executionContext;
    }

    protected void buildContext() {
        this.context = Context.newBuilder("python")
                .engine(plugin.getPythonEngine())
                .allowAllAccess(true)
                .allowHostAccess(HostAccess.ALL)
                .allowHostClassLookup(_ -> true)
                .build();
    }

    protected void doInit() {
        List<String> wheelPaths = plugin.getWheelPaths();
        if (!wheelPaths.isEmpty()) {
            StringBuilder sb = new StringBuilder("import sys\n");
            for (String path : wheelPaths) {
                sb.append(String.format("sys.path.insert(0, '%s')\n", path));
            }
            context.eval("python", sb.toString());
        }

        Value bindings = context.getBindings("python");
        bindings.putMember("__identifier", plugin.getIdentifier());
        bindings.putMember("__manifest", plugin.getManifest());
        bindings.putMember("__data_directory", plugin.getDataDirectory());
        bindings.putMember("__context", executionContext.getValue());
        bindings.putMember("__plugin", plugin);
        context.eval("python",
                "import pytale.plugin._plugin\n" +
                        "pytale.plugin._plugin._init_plugin" +
                        "(__identifier, __manifest, __data_directory, __context, __plugin)");

        initContextBindings(bindings);

        String moduleName = plugin.getManifest().getName().replace("-", "_");
        context.eval("python", "import " + moduleName);

        logger.atInfo().log("Python context initialized");
    }

    /**
     * Hook for context-specific Python bindings, evaluated after the core plugin init but
     * before the plugin module is imported. No-op by default; overridden by contexts that
     * inject extra objects (e.g. the world). Runs inside the context.
     */
    protected void initContextBindings(Value bindings) {
        // no-op
    }

    /**
     * Acquires the context lock, sets the correct classloader, enters the GraalPy context,
     * runs {@code task}, then leaves and releases. Safe to call from any thread.
     */
    public void withContext(Runnable task) {
        ClassLoader prev = Thread.currentThread().getContextClassLoader();
        Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
        lock.lock();
        try {
            context.enter();
            try {
                task.run();
            } finally {
                context.leave();
            }
        } finally {
            lock.unlock();
            Thread.currentThread().setContextClassLoader(prev);
        }
    }

    public void init() {
        try {
            buildContext();
            withContext(this::doInit);
        } catch (PolyglotException e) {
            logger.atWarning().log("Python error during initialization: %s", e.getMessage());
        } catch (Exception e) {
            logger.atSevere().log("Failed to initialize context: %s", e.getMessage());
        }
    }

    public void invokeEventHandler(int index, IEvent<?> event) {
        if (context == null) {
            logger.atWarning().log("Context not initialized, cannot invoke event handler");
            return;
        }
        withContext(() -> {
            try {
                context.getBindings("python").putMember("__event_index", index);
                context.getBindings("python").putMember("__event_obj", event);
                context.eval("python",
                        "from pytale.events._registry import _execute_handler\n" +
                                "_execute_handler(__event_index, __event_obj)");
            } catch (PolyglotException e) {
                logger.atWarning().log("Python error in event handler %d: %s", index, e.getMessage());
            }
        });
    }

    public Context getContext() {
        return context;
    }

    public void close() {
        close(false);
    }

    public void close(boolean cancelIfExecuting) {
        if (context != null) {
            // cancelIfExecuting=true: context.close() cancels any running computation and is
            // thread-safe by the GraalPy API contract — acquiring the lock would deadlock.
            if (!cancelIfExecuting) {
                lock.lock();
            }
            try {
                context.close(cancelIfExecuting);
                logger.atInfo().log("Python context closed");
            } catch (Exception e) {
                logger.atSevere().log("Error closing context: %s", e.getMessage());
            } finally {
                if (!cancelIfExecuting) {
                    lock.unlock();
                }
            }
        }
    }
}
