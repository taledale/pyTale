package dev.taledale.pytale.context.world;

import com.hypixel.hytale.event.IEvent;
import com.hypixel.hytale.server.core.universe.world.World;
import dev.taledale.pytale.AbstractPythonPlugin;
import dev.taledale.pytale.ExecutionContext;
import dev.taledale.pytale.PyTale;
import dev.taledale.pytale.context.PythonContext;
import org.graalvm.polyglot.PolyglotException;

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
        world.execute(() -> {
            ClassLoader prev = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                super.init();
            } finally {
                Thread.currentThread().setContextClassLoader(prev);
            }
        });
    }

    public void eval(String code) {
        world.execute(() -> {
            if (context == null) {
                logger.atWarning().log("Context not initialized, cannot eval");
                return;
            }
            ClassLoader prev = Thread.currentThread().getContextClassLoader();
            try {
                Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
                context.eval("python", code);
            } catch (PolyglotException e) {
                logger.atWarning().log("Python error: %s", e.getMessage());
            } finally {
                Thread.currentThread().setContextClassLoader(prev);
            }
        });
    }

    public void invokeEventHandler(int index, IEvent<?> event) {
        if (context == null) {
            logger.atWarning().log("Context not initialized, cannot invoke event handler");
            return;
        }
        ClassLoader prev = Thread.currentThread().getContextClassLoader();
        try {
            Thread.currentThread().setContextClassLoader(PyTale.get().getClass().getClassLoader());
            context.enter();
            try {
                context.getBindings("python").putMember("__event_index", index);
                context.getBindings("python").putMember("__event_obj", event);
                context.eval("python",
                        "from pytale.events._registry import _execute_handler\n" +
                                "_execute_handler(__event_index, __event_obj)");
            } catch (PolyglotException e) {
                logger.atWarning().log("Python error in event handler %d: %s", index, e.getMessage());
            } finally {
                context.leave();
            }
        } finally {
            Thread.currentThread().setContextClassLoader(prev);
        }
    }

    public World getWorld() {
        return world;
    }
}
