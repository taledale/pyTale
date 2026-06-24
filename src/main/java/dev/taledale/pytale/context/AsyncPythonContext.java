package dev.taledale.pytale.context;

import com.hypixel.hytale.event.IAsyncEvent;
import com.hypixel.hytale.logger.HytaleLogger;
import dev.taledale.pytale.AbstractPythonPlugin;
import dev.taledale.pytale.PyTale;
import org.graalvm.polyglot.PolyglotException;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.LinkedBlockingQueue;

/**
 * A Python context dedicated to {@code IAsyncEvent} handlers.
 *
 * <p>A single daemon thread ({@code pytale-async-event-loop}) owns the GraalPy context for its
 * entire lifetime: it enters the context once and runs an asyncio event loop that drains
 * {@link #queue}. Events are enqueued from arbitrary dispatcher threads (Netty/FJP) via
 * {@link #enqueue} as plain Java objects — that path never touches the GraalPy context, so it
 * never contends with the running loop.
 */
public class AsyncPythonContext extends PythonContext {
    private static final long SHUTDOWN_TIMEOUT_MS = 5000;

    private final LinkedBlockingQueue<QueuedAsyncEvent> queue = new LinkedBlockingQueue<>();
    private Thread asyncThread;

    public AsyncPythonContext(AbstractPythonPlugin plugin, HytaleLogger logger) {
        super(plugin, logger, ExecutionContext.GENERAL);
    }

    @Override
    public void init() {
        try {
            buildContext();
            withContext(() -> {
                doInit();
                context.getBindings("python").putMember("__async_queue", queue);
            });
            startAsyncThread();
        } catch (PolyglotException e) {
            logger.atWarning().log("Python error during async initialization: %s", e.getMessage());
        } catch (Exception e) {
            logger.atSevere().log("Failed to initialize async context: %s", e.getMessage());
        }
    }

    private void startAsyncThread() {
        asyncThread = new Thread(() -> {
            ClassLoader prev = Thread.currentThread().getContextClassLoader();
            Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
            context.enter();
            try {
                context.eval("python",
                        "from pytale.events._registry import _start_loop\n" +
                                "_start_loop(__async_queue)");
            } catch (PolyglotException e) {
                logger.atWarning().log("Async event loop terminated: %s", e.getMessage());
            } finally {
                context.leave();
                Thread.currentThread().setContextClassLoader(prev);
            }
        }, "pytale-async-event-loop");
        asyncThread.setDaemon(true);
        asyncThread.start();
        logger.atInfo().log("Async event loop started");
    }

    public void enqueue(int index, IAsyncEvent<?> event, CompletableFuture<IAsyncEvent<?>> future) {
        queue.offer(new QueuedAsyncEvent(index, event, future));
    }

    @Override
    public void close(boolean cancelIfExecuting) {
        // Signal the loop to stop, then wait for it to drain and leave the context before closing.
        queue.offer(new QueuedAsyncEvent(-1, null, null));
        if (asyncThread != null) {
            try {
                asyncThread.join(SHUTDOWN_TIMEOUT_MS);
                if (asyncThread.isAlive()) {
                    logger.atWarning().log(
                            "Async event loop did not stop within %d ms, forcing close", SHUTDOWN_TIMEOUT_MS);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        super.close(cancelIfExecuting);
    }
}
