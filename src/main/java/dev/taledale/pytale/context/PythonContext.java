package dev.taledale.pytale.context;

import com.hypixel.hytale.event.IEvent;
import com.hypixel.hytale.logger.HytaleLogger;
import dev.taledale.pytale.AbstractPythonPlugin;
import dev.taledale.pytale.PyTale;
import dev.taledale.pytale.command.PythonCommandContext;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.HostAccess;
import org.graalvm.polyglot.PolyglotException;
import org.graalvm.polyglot.Value;
import org.graalvm.python.embedding.GraalPyResources;
import org.graalvm.python.embedding.VirtualFileSystem;

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
        // The plugin's Python code and its dependencies are pip-installed into a venv that is
        // bundled in the plugin jar under the GraalPy Virtual Filesystem resource root
        // "GRAALPY-VFS/TaleDale/<module>". GraalPyResources points sys.path/sys.executable at that
        // venv, so packages import directly from the jar with no temp extraction (only native libs
        // are extracted on demand by the VFS). The resource-loading class is anchored to the plugin
        // jar (see AbstractPythonPlugin#getResourceAnchorClass) so the VFS metadata resolves
        // regardless of how the framework is deployed.
        VirtualFileSystem vfs = VirtualFileSystem.newBuilder()
                .resourceDirectory("GRAALPY-VFS/TaleDale/" + moduleName())
                .resourceLoadingClass(plugin.getResourceAnchorClass())
                .build();

        // GraalPyResources.forVirtualFileSystem configures the VFS filesystem and Python resource
        // options. We must NOT call allowAllAccess(true) (it would replace the VFS with IOAccess.ALL).
        // allowHostClassLookup is added so Python can resolve Java event classes.
        this.context = Context.newBuilder()
                .apply(GraalPyResources.forVirtualFileSystem(vfs))
                .engine(plugin.getPythonEngine())
                .allowHostAccess(HostAccess.ALL)
                .allowHostClassLookup(_ -> true)
                .build();
    }

    /** Python module / VFS resource name for this plugin (manifest name with '-' replaced by '_'). */
    protected String moduleName() {
        return plugin.getManifest().getName().replace("-", "_");
    }

    protected void doInit() {
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

        context.eval("python", "import " + moduleName());

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

    public void invokeCommandHandler(int index, PythonCommandContext pyCtx) {
        if (context == null) {
            logger.atWarning().log("Context not initialized, cannot invoke command handler");
            return;
        }
        withContext(() -> {
            try {
                context.getBindings("python").putMember("__cmd_index", index);
                context.getBindings("python").putMember("__cmd_ctx", pyCtx);
                context.eval("python",
                        "from pytale.commands._registry import _execute_command\n" +
                                "_execute_command(__cmd_index, __cmd_ctx)");
            } catch (PolyglotException e) {
                logger.atWarning().log("Python error in command handler %d: %s", index, e.getMessage());
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
