package dev.taledale.pytale.context.world;

import com.hypixel.hytale.event.IEventRegistry;
import com.hypixel.hytale.logger.HytaleLogger;
import com.hypixel.hytale.server.core.universe.world.World;
import com.hypixel.hytale.server.core.universe.world.events.AddWorldEvent;
import com.hypixel.hytale.server.core.universe.world.events.RemoveWorldEvent;
import dev.taledale.pytale.AbstractPythonPlugin;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class WorldContextManager {
    private final HytaleLogger logger;
    private final AbstractPythonPlugin plugin;
    private final Map<String, WorldPythonContext> contexts = new ConcurrentHashMap<>();

    public WorldContextManager(AbstractPythonPlugin plugin) {
        this.plugin = plugin;
        this.logger = plugin.getLogger().getSubLogger("[Worlds]");
    }

    public void start() {
        logger.atInfo().log("Starting world context manager");
        IEventRegistry eventRegistry = plugin.getEventRegistry();
        eventRegistry.registerGlobal(AddWorldEvent.class, this::onAddWorld);
        eventRegistry.registerGlobal(RemoveWorldEvent.class, this::onRemoveWorld);
    }

    private void onAddWorld(AddWorldEvent event) {
        World world = event.getWorld();
        String worldName = world.getName();
        logger.atInfo().log("World added: %s", worldName);

        WorldPythonContext context = new WorldPythonContext(plugin, world);
        context.init();
        contexts.put(worldName, context);
    }

    private void onRemoveWorld(RemoveWorldEvent event) {
        World world = event.getWorld();
        String worldName = world.getName();
        logger.atInfo().log("World removed: %s", worldName);

        WorldPythonContext context = contexts.remove(worldName);
        if (context != null) {
            context.close(true);
        }
    }

    public WorldPythonContext getContext(World world) {
        return contexts.get(world.getName());
    }

    /**
     * Schedule a task at {@code index} to run on {@code world}'s tick thread, in that world's
     * own Python context. Safe to call from any thread/context.
     *
     * <p>Returns a status string rather than throwing: a Java exception raised inside a Python
     * host-interop call does not propagate as a catchable exception on the Python side (it
     * unwinds straight past any {@code except} clause to the enclosing {@code context.eval()}
     * call in Java instead), so failures must be signalled back to Python as an ordinary
     * (host-safe) return value that Python code can branch on.
     *
     * @return {@code "ok"} if scheduled, {@code "no_context"} if the world has no initialized
     *     context yet (e.g. still starting up or already removed), {@code "not_accepting"} if
     *     the world's tick thread has stopped accepting tasks (shutting down).
     */
    public String executeTask(World world, int index, Object[] args, Map<String, Object> kwargs) {
        WorldPythonContext context = getContext(world);
        if (context == null) {
            logger.atWarning().log(
                    "No context for world %s, cannot schedule task %d", world.getName(), index);
            return "no_context";
        }
        return context.invokeScheduledTask(index, args, kwargs);
    }

    public void shutdown() {
        logger.atInfo().log("Shutting down world context manager");
        for (WorldPythonContext context : contexts.values()) {
            context.close(true);
        }
        contexts.clear();
    }
}
