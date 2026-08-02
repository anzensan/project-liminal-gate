package org.liminalgate.android;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class HealthzTest {
    @Test public void acceptsOnlyTheExpectedHealthBuildId() {
        assertTrue(Healthz.hasExpectedBuildId("{\"service\":\"project-liminal-gate\",\"status\":\"ok\",\"build_id\":\"abc\"}", "abc"));
        assertFalse(Healthz.hasExpectedBuildId("{\"service\":\"project-liminal-gate\",\"status\":\"ok\",\"build_id\":\"other\"}", "abc"));
        assertFalse(Healthz.hasExpectedBuildId("{\"status\":\"ok\",\"build_id\":\"abc\"}", "abc"));
        assertFalse(Healthz.hasExpectedBuildId("{\"status\":\"ok\"}", "abc"));
    }

    @Test public void redactsPathsAndUrlsFromCopiedFailures() {
        String text = Healthz.redact(new IllegalStateException("http://secret.example/a /data/user/0/private"));
        assertFalse(text.contains("secret.example"));
        assertFalse(text.contains("/data/user"));
        assertTrue(text.contains("IllegalStateException"));
    }

    @Test public void redactsNewlinesFromCopiedFailures() {
        String text = Healthz.redact(new IllegalStateException("first\nsecond"));
        assertFalse(text.contains("\n"));
    }
}
