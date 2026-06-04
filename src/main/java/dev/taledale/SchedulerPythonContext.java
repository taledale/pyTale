package dev.taledale;

import com.hypixel.hytale.logger.HytaleLogger;
import com.hypixel.hytale.server.core.HytaleServer;
import com.hypixel.hytale.server.core.task.TaskRegistry;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.HostAccess;
import org.graalvm.polyglot.PolyglotException;
import org.graalvm.polyglot.Value;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class SchedulerPythonContext {
    private final AtomicReference<Context> context = new AtomicReference<>();
    private final TaskRegistry taskRegistry;
    private final HytaleLogger logger;

    public SchedulerPythonContext(TaskRegistry taskRegistry) {
        this.taskRegistry = taskRegistry;
        this.logger = PyTale.get().getLogger().getSubLogger("SchedulerContext");

        initializeContextOnScheduler();
    }

    private void initializeContextOnScheduler() {
        CountDownLatch latch = new CountDownLatch(1);

        HytaleServer.SCHEDULED_EXECUTOR.submit(() -> {
            ClassLoader previousCl = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                Context ctx = Context.newBuilder("python")
                        .allowAllAccess(true)
                        .allowHostAccess(HostAccess.ALL)
                        .allowHostClassLookup(_ -> true)
                        .build();

                context.set(ctx);
                ctx.getPolyglotBindings().putMember("_scheduler_api", new SchedulerAPI(this));
                logger.atInfo().log("Scheduler Python context initialized");
            } finally {
                Thread.currentThread().setContextClassLoader(previousCl);
                latch.countDown();
            }
        });

        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                logger.atWarning().log("Scheduler context initialization timed out");
            }
        } catch (InterruptedException e) {
            logger.atWarning().log("Scheduler context initialization interrupted");
            Thread.currentThread().interrupt();
        }
    }

    public void eval(String code) {
        HytaleServer.SCHEDULED_EXECUTOR.submit(() -> {
            Context ctx = context.get();
            if (ctx == null) {
                logger.atWarning().log("Context not initialized, cannot eval");
                return;
            }

            ClassLoader previousCl = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                ctx.eval("python", code);
            } catch (PolyglotException e) {
                logger.atWarning().log("Python error: %s", e.getMessage());
            } finally {
                Thread.currentThread().setContextClassLoader(previousCl);
            }
        });
    }

    public void scheduleTask(long delayMs, long periodMs, Value handler) {
        HytaleServer.SCHEDULED_EXECUTOR.submit(() -> {
            try {
                if (periodMs > 0) {
                    ScheduledFuture<?> rawFuture = HytaleServer.SCHEDULED_EXECUTOR.scheduleAtFixedRate(
                            () -> executeHandler(handler),
                            delayMs,
                            periodMs,
                            TimeUnit.MILLISECONDS);
                    @SuppressWarnings({ "unchecked", "rawtypes" })
                    ScheduledFuture<Void> future = (ScheduledFuture) rawFuture;
                    taskRegistry.registerTask(future);
                    logger.atInfo().log("Scheduled repeating task: delay=%dms, period=%dms", delayMs, periodMs);
                } else {
                    ScheduledFuture<?> rawFuture = HytaleServer.SCHEDULED_EXECUTOR.schedule(
                            () -> executeHandler(handler),
                            delayMs,
                            TimeUnit.MILLISECONDS);
                    @SuppressWarnings({ "unchecked", "rawtypes" })
                    ScheduledFuture<Void> future = (ScheduledFuture) rawFuture;
                    taskRegistry.registerTask(future);
                    logger.atInfo().log("Scheduled one-time task: delay=%dms", delayMs);
                }
            } catch (Exception e) {
                logger.atSevere().log("Failed to schedule task: %s", e.getMessage());
            }
        });
    }

    private void executeHandler(Value handler) {
        ClassLoader previousCl = Thread.currentThread().getContextClassLoader();
        try {
            Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
            handler.execute();
        } catch (Exception e) {
            logger.atWarning().log("Task execution error: %s", e.getMessage());
        } finally {
            Thread.currentThread().setContextClassLoader(previousCl);
        }
    }

    public void close() {
        HytaleServer.SCHEDULED_EXECUTOR.execute(() -> {
            Context ctx = context.get();
            if (ctx != null) {
                try {
                    ctx.close();
                    logger.atInfo().log("Scheduler Python context closed");
                } catch (Exception e) {
                    logger.atSevere().log("Error closing context: %s", e.getMessage());
                }
            }
        });
    }

    public static class SchedulerAPI {
        private final SchedulerPythonContext context;

        public SchedulerAPI(SchedulerPythonContext context) {
            this.context = context;
        }

        public void schedule(long delayMs, long periodMs, Value handler) {
            context.scheduleTask(delayMs, periodMs, handler);
        }
    }
}
