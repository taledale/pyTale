package dev.taledale;

import com.hypixel.hytale.logger.HytaleLogger;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class PluginLoader {
    private final SingleThreadPythonRuntime runtime;
    private final HytaleLogger logger;

    public PluginLoader(SingleThreadPythonRuntime runtime) {
        this.runtime = runtime;
        this.logger = PyTale.get().getLogger().getSubLogger("PluginLoader");
    }

    public void loadAll() {
        try {
            Path pluginsDir = PyTale.get().getDataDirectory().resolve("plugins");
            if (!Files.exists(pluginsDir)) {
                Files.createDirectories(pluginsDir);
                logger.atInfo().log("Plugins directory created: %s", pluginsDir);
                return;
            }

            logger.atInfo().log("Scanning plugins directory: %s", pluginsDir);
            try (Stream<Path> files = Files.list(pluginsDir)) {
                files.filter(p -> p.toString().endsWith(".py"))
                    .forEach(this::loadPythonScript);
            }

        } catch (IOException e) {
            logger.atSevere().log("Error loading plugins: %s", e.getMessage());
        }
    }

    private void loadPythonScript(Path scriptPath) {
        try {
            logger.atInfo().log("Loading Python script: %s", scriptPath.getFileName());
            String code = Files.readString(scriptPath);
            runtime.eval(code);
            logger.atInfo().log("Loaded: %s", scriptPath.getFileName());
        } catch (Exception e) {
            logger.atWarning().log("Error loading plugin %s: %s", scriptPath.getFileName(), e.getMessage());
        }
    }

    public void shutdown() {
        logger.atInfo().log("Shutting down plugin loader");
        runtime.close();
    }
}
