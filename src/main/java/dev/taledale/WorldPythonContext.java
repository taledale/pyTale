package dev.taledale;

import com.hypixel.hytale.logger.HytaleLogger;
import com.hypixel.hytale.server.core.universe.world.World;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.HostAccess;
import org.graalvm.polyglot.PolyglotException;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class WorldPythonContext {
    private final World world;
    private final HytaleLogger logger;
    private Context context;

    public WorldPythonContext(World world) {
        this.world = world;
        this.logger = PyTale.get().getLogger().getSubLogger("[" + world.getName() + "]");
    }

    public void initialize() {
        CountDownLatch latch = new CountDownLatch(1);

        world.execute(() -> {
            ClassLoader previousCl = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                context = Context.newBuilder("python")
                    .allowAllAccess(true)
                    .allowHostAccess(HostAccess.ALL)
                    .allowHostClassLookup(_ -> true)
                    .build();
                logger.atInfo().log("World Python context initialized");
            } catch (Exception e) {
                logger.atSevere().log("Failed to initialize context: %s", e.getMessage());
            } finally {
                Thread.currentThread().setContextClassLoader(previousCl);
                latch.countDown();
            }
        });

        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                logger.atWarning().log("World context initialization timed out");
            }
        } catch (InterruptedException e) {
            logger.atWarning().log("World context initialization interrupted");
            Thread.currentThread().interrupt();
        }
    }

    public void eval(String code) {
        world.execute(() -> {
            if (context == null) {
                logger.atWarning().log("Context not initialized, cannot eval");
                return;
            }

            ClassLoader previousCl = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                context.eval("python", code);
            } catch (PolyglotException e) {
                logger.atWarning().log("Python error: %s", e.getMessage());
            } finally {
                Thread.currentThread().setContextClassLoader(previousCl);
            }
        });
    }

    public void close() {
        CountDownLatch latch = new CountDownLatch(1);

        world.execute(() -> {
            if (context != null) {
                try {
                    context.close();
                    logger.atInfo().log("World Python context closed");
                } catch (Exception e) {
                    logger.atSevere().log("Error closing context: %s", e.getMessage());
                }
            }
            latch.countDown();
        });

        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                logger.atWarning().log("World context close timed out");
            }
        } catch (InterruptedException e) {
            logger.atWarning().log("World context close interrupted");
            Thread.currentThread().interrupt();
        }
    }

    public World getWorld() {
        return world;
    }
}
