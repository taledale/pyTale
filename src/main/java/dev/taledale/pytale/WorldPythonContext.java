package dev.taledale.pytale;

import com.hypixel.hytale.logger.HytaleLogger;
import com.hypixel.hytale.server.core.universe.world.World;
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.PolyglotException;

public class WorldPythonContext {
    private final World world;
    private final HytaleLogger logger;
    private final AbstractPythonPlugin plugin;
    private Context context;

    public WorldPythonContext(AbstractPythonPlugin plugin, World world) {
        this.plugin = plugin;
        this.world = world;
        this.logger = plugin.getLogger().getSubLogger("[" + world.getName() + "]");
    }

    public void initialize() {
        world.execute(() -> {
            ClassLoader previousCl = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                context = PythonContextFactory.newContext();

                // Add wheel files to sys.path
                java.util.List<String> wheelPaths = plugin.getWheelPaths();
                if (!wheelPaths.isEmpty()) {
                    StringBuilder setupCode = new StringBuilder();
                    setupCode.append("import sys\n");
                    for (String wheelPath : wheelPaths) {
                        setupCode.append(String.format("sys.path.insert(0, '%s')\n", wheelPath));
                    }
                    context.eval("python", setupCode.toString());
                }

                logger.atInfo().log("World Python context initialized");
            } catch (Exception e) {
                logger.atSevere().log("Failed to initialize context: %s", e.getMessage());
            } finally {
                Thread.currentThread().setContextClassLoader(previousCl);
            }
        });
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
        world.execute(() -> {
            if (context != null) {
                try {
                    context.close();
                    logger.atInfo().log("World Python context closed");
                } catch (Exception e) {
                    logger.atSevere().log("Error closing context: %s", e.getMessage());
                }
            }
        });
    }

    public World getWorld() {
        return world;
    }
}
