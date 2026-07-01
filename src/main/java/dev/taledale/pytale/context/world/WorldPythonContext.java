package dev.taledale.pytale.context.world;

import com.hypixel.hytale.logger.sentry.SkipSentryException;
import com.hypixel.hytale.server.core.universe.world.World;
import dev.taledale.pytale.AbstractPythonPlugin;
import dev.taledale.pytale.context.ExecutionContext;
import dev.taledale.pytale.context.PythonContext;
import org.graalvm.polyglot.PolyglotException;
import org.graalvm.polyglot.Value;

import java.util.Map;

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
        world.execute(super::init);
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

    /**
     * @return {@code "ok"} if the task was successfully enqueued onto the world thread (it may
     *     still fail once it actually runs; see the try/catch inside), {@code "no_context"} if
     *     this context isn't initialized yet, {@code "not_accepting"} if the world's tick thread
     *     has stopped accepting tasks.
     */
    public String invokeScheduledTask(int index, Object[] args, Map<String, Object> kwargs) {
        if (context == null) {
            logger.atWarning().log("Context not initialized, cannot invoke scheduled task");
            return "no_context";
        }
        try {
            world.execute(() -> withContext(() -> {
                try {
                    context.getBindings("python").putMember("__task_index", index);
                    context.getBindings("python").putMember("__task_args", args);
                    context.getBindings("python").putMember("__task_kwargs", kwargs);
                    context.eval("python",
                            "from pytale.world._registry import _execute_task\n" +
                                    "_execute_task(__task_index, tuple(__task_args), dict(__task_kwargs))");
                } catch (PolyglotException e) {
                    logger.atWarning().log("Python error in scheduled task %d: %s", index, e.getMessage());
                }
            }));
            return "ok";
        } catch (SkipSentryException e) {
            logger.atWarning().log(
                    "World %s is not accepting tasks, dropping scheduled task %d", world.getName(), index);
            return "not_accepting";
        }
    }
}
