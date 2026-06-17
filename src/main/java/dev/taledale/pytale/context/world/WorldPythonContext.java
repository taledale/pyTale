package dev.taledale.pytale.context.world;

import com.hypixel.hytale.server.core.universe.world.World;
import dev.taledale.pytale.AbstractPythonPlugin;
import dev.taledale.pytale.ExecutionContext;
import dev.taledale.pytale.context.PythonContext;
import org.graalvm.polyglot.Value;

public class WorldPythonContext extends PythonContext {
    private final World world;

    public WorldPythonContext(AbstractPythonPlugin plugin, World world) {
        super(
                plugin,
                plugin.getLogger().getSubLogger("[" + world.getName() + "]"),
                ExecutionContext.WORLD);
        this.world = world;
    }

    @Override
    public void init() {
        world.execute(() -> super.init());
    }

    @Override
    protected void initContextBindings(Value bindings) {
        bindings.putMember("__world", world);
        context.eval("python",
                "import pytale.world._world\n" +
                        "pytale.world._world._init_world(__world)");
    }

    public void eval(String code) {
        world.execute(() -> {
            if (context == null) {
                logger.atWarning().log("Context not initialized, cannot eval");
                return;
            }
            withContext(() -> context.eval("python", code));
        });
    }

    public World getWorld() {
        return world;
    }
}
