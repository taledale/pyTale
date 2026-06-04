package dev.taledale;

import com.hypixel.hytale.logger.HytaleLogger;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.HostAccess;
import org.graalvm.polyglot.PolyglotException;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class SingleThreadPythonRuntime {
    private final ExecutorService executor;
    private Context context;
    private final HytaleLogger logger;

    public SingleThreadPythonRuntime() {
        this.logger = PyTale.get().getLogger().getSubLogger("PythonRuntime");
        this.executor = Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "PyTale-Runtime");
            t.setDaemon(false);
            return t;
        });

        // Initialize context on the executor thread
        try {
            executor.submit(() -> {
                ClassLoader previousCl = Thread.currentThread().getContextClassLoader();
                try {
                    Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                    context = Context.newBuilder("python")
                        .allowAllAccess(true)
                        .allowHostAccess(HostAccess.ALL)
                        .allowHostClassLookup(_ -> true)
                        .build();
                    logger.atInfo().log("Python context initialized");
                } finally {
                    Thread.currentThread().setContextClassLoader(previousCl);
                }
            }).get();
        } catch (Exception e) {
            logger.atSevere().log("Failed to initialize Python context: %s", e.getMessage());
            throw new RuntimeException(e);
        }
    }

    public void eval(String code) {
        submit(() -> {
            try {
                context.eval("python", code);
            } catch (PolyglotException e) {
                logger.atWarning().log("Python error: %s", e.getMessage());
            }
        });
    }

    public void submit(Runnable task) {
        executor.submit(() -> {
            ClassLoader previousCl = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                task.run();
            } finally {
                Thread.currentThread().setContextClassLoader(previousCl);
            }
        });
    }

    public void close() {
        executor.submit(() -> {
            if (context != null) {
                try {
                    context.close();
                    logger.atInfo().log("Python context closed");
                } catch (Exception e) {
                    logger.atSevere().log("Error closing context: %s", e.getMessage());
                }
            }
        });

        executor.shutdown();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
