package dev.taledale.pytale;

/**
 * Execution context for Python code in pyTale plugins.
 * Must match pytale.plugin.ExecutionContext values.
 */
public enum ExecutionContext {
    GENERAL(0),
    SCHEDULER(1),
    WORLD(2);

    private final int value;

    ExecutionContext(int value) {
        this.value = value;
    }

    public int getValue() {
        return value;
    }
}
