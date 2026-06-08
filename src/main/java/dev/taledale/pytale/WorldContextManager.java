package dev.taledale.pytale;

import com.hypixel.hytale.event.IEventRegistry;
import com.hypixel.hytale.logger.HytaleLogger;
import com.hypixel.hytale.server.core.universe.world.World;
import com.hypixel.hytale.server.core.universe.world.events.AddWorldEvent;
import com.hypixel.hytale.server.core.universe.world.events.RemoveWorldEvent;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class WorldContextManager {
    private final HytaleLogger logger;
    private final AbstractPythonPlugin plugin;
    private final IEventRegistry eventRegistry;
    private final Map<String, WorldPythonContext> contexts = new ConcurrentHashMap<>();

    public WorldContextManager(AbstractPythonPlugin plugin) {
        this.plugin = plugin;
        this.logger = plugin.getLogger().getSubLogger("[Worlds]");
        this.eventRegistry = plugin.getEventRegistry();
    }

    public void start() {
        logger.atInfo().log("Starting world context manager");
        eventRegistry.registerGlobal(AddWorldEvent.class, this::onAddWorld);
        eventRegistry.registerGlobal(RemoveWorldEvent.class, this::onRemoveWorld);
    }

    private void onAddWorld(AddWorldEvent event) {
        World world = event.getWorld();
        String worldName = world.getName();
        logger.atInfo().log("World added: %s", worldName);

        WorldPythonContext context = new WorldPythonContext(plugin, world);
        context.initialize();
        contexts.put(worldName, context);
    }

    private void onRemoveWorld(RemoveWorldEvent event) {
        World world = event.getWorld();
        String worldName = world.getName();
        logger.atInfo().log("World removed: %s", worldName);

        WorldPythonContext context = contexts.remove(worldName);
        if (context != null) {
            context.close();
        }
    }

    public WorldPythonContext getContext(World world) {
        return contexts.get(world.getName());
    }

    public void shutdown() {
        logger.atInfo().log("Shutting down world context manager");
        for (WorldPythonContext context : contexts.values()) {
            context.close();
        }
        contexts.clear();
    }
}
