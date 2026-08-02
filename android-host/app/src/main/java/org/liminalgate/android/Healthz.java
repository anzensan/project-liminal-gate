package org.liminalgate.android;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Small dependency-free helpers used before Unity is allowed to initialize. */
final class Healthz {
    private static final Pattern SERVICE = Pattern.compile("\\\"service\\\"\\s*:\\s*\\\"project-liminal-gate\\\"");
    private static final Pattern STATUS = Pattern.compile("\\\"status\\\"\\s*:\\s*\\\"ok\\\"");
    private static final Pattern BUILD_ID = Pattern.compile("\\\"build_id\\\"\\s*:\\s*\\\"([^\\\"]*)\\\"");

    private Healthz() { }

    static boolean hasExpectedBuildId(String json, String expectedBuildId) {
        if (json == null || expectedBuildId == null) return false;
        Matcher matcher = BUILD_ID.matcher(json);
        return SERVICE.matcher(json).find()
                && STATUS.matcher(json).find()
                && matcher.find()
                && expectedBuildId.equals(matcher.group(1));
    }

    static String redact(Throwable failure) {
        if (failure == null) return "none";
        String message = failure.getMessage();
        if (message == null || message.isEmpty()) return failure.getClass().getSimpleName();
        // Paths, URLs, and newlines can expose local details in copied reports.
        message = message.replaceAll("(?:[A-Za-z][A-Za-z0-9+.-]*://|/)[^\\s]+", "[redacted]");
        message = message.replaceAll("[\\r\\n\\t]+", " ").trim();
        return failure.getClass().getSimpleName() + ": " + message;
    }
}
