package org.liminalgate.android;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.res.Configuration;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.view.InputEvent;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.lang.reflect.Constructor;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Hosts the original Unity player only after the embedded compatibility service
 * is reachable through the same loopback HTTP boundary the client uses.
 *
 * Unity is deliberately loaded by reflection: source-only host builds have no
 * redistributed Unity classes, while the private APK merger supplies them.
 */
public final class HostedActivity extends Activity {
    private static final String HEALTH_URL = "http://127.0.0.1:8002/healthz";
    private static final int READY_ATTEMPTS = 240;
    private static final long RETRY_DELAY_MS = 250;
    private static final ExecutorService STARTUP = Executors.newSingleThreadExecutor();
    private static final AtomicReference<CompletableFuture<Void>> READINESS = new AtomicReference<>();

    private LinearLayout gate;
    private TextView status;
    private Button retry;
    private Button copy;
    private volatile Throwable startupFailure;
    private volatile String failureStage = "none";
    private volatile Object unityPlayer;
    private volatile boolean destroyed;
    private volatile boolean resumed;
    private volatile boolean focused;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        showGate("Starting local service…", false);
        awaitService();
    }

    private void awaitService() {
        CompletableFuture<Void> ready = ensureStarted();
        ready.whenComplete((ignored, failure) -> runOnUiThread(() -> {
            if (destroyed) return;
            if (failure != null) {
                startupFailure = unwrap(failure);
                showGate("Local service failed to start.", true);
                return;
            }
            showUnity();
        }));
    }

    private CompletableFuture<Void> ensureStarted() {
        CompletableFuture<Void> existing = READINESS.get();
        if (existing != null) return existing;
        CompletableFuture<Void> candidate = CompletableFuture.runAsync(this::startAndProbe, STARTUP);
        if (READINESS.compareAndSet(null, candidate)) return candidate;
        return READINESS.get();
    }

    private void startAndProbe() {
        try {
            if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
            ApplicationInfo app = getApplicationInfo();
            Python.getInstance().getModule("liminal_gate.android_entrypoint")
                    .callAttr("start", app.sourceDir, getFilesDir().getAbsolutePath(), BuildConfig.HOST_BUILD_ID);
        } catch (Throwable failure) {
            failureStage = "python_start";
            throw new StartupException("python_start", failure);
        }
        Throwable last = null;
        for (int attempt = 0; attempt < READY_ATTEMPTS; attempt++) {
            try {
                if (healthMatches()) return;
            } catch (Throwable failure) {
                last = failure;
            }
            try { Thread.sleep(RETRY_DELAY_MS); }
            catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("service readiness interrupted", interrupted);
            }
        }
        failureStage = "healthz";
        throw new StartupException("healthz", new IllegalStateException("service did not report the expected build ID", last));
    }

    private boolean healthMatches() throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(HEALTH_URL).openConnection();
        connection.setConnectTimeout(500);
        connection.setReadTimeout(500);
        connection.setRequestMethod("GET");
        try {
            if (connection.getResponseCode() != HttpURLConnection.HTTP_OK) return false;
            try (InputStream input = connection.getInputStream(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[1024];
                for (int read; (read = input.read(buffer)) != -1;) output.write(buffer, 0, read);
                return Healthz.hasExpectedBuildId(output.toString(StandardCharsets.UTF_8.name()), BuildConfig.HOST_BUILD_ID);
            }
        } finally { connection.disconnect(); }
    }

    private void showGate(String message, boolean failed) {
        gate = new LinearLayout(this);
        gate.setOrientation(LinearLayout.VERTICAL);
        gate.setGravity(Gravity.CENTER);
        gate.setPadding(48, 48, 48, 48);
        gate.setBackgroundColor(Color.BLACK);
        status = new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setTextSize(18);
        status.setGravity(Gravity.CENTER);
        status.setText(message);
        gate.addView(status, new LinearLayout.LayoutParams(-1, -2));
        if (failed) {
            retry = new Button(this); retry.setText("Retry"); retry.setOnClickListener(view -> retryStartup());
            copy = new Button(this); copy.setText("Copy diagnostics"); copy.setOnClickListener(view -> copyDiagnostics());
            gate.addView(retry); gate.addView(copy);
        }
        setContentView(gate);
    }

    private void retryStartup() {
        READINESS.set(null);
        startupFailure = null;
        failureStage = "none";
        showGate("Retrying local service…", false);
        awaitService();
    }

    private void copyDiagnostics() {
        // This newline-delimited contract is intentionally stable for support
        // reports. It contains no filesystem path, APK path, or Python trace.
        String report = "host_diagnostics_version=1\nstate=error\nstage=" + failureStage
                + "\nbuild_id=" + BuildConfig.HOST_BUILD_ID
                + "\nhealth=127.0.0.1:8002/healthz\nerror=" + Healthz.redact(startupFailure);
        ((ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE))
                .setPrimaryClip(ClipData.newPlainText("Liminal Gate diagnostics", report));
        status.setText("Diagnostics copied. Retry when ready.");
    }

    private void showUnity() {
        try {
            Class<?> type = Class.forName("com.unity3d.player.UnityPlayer");
            Constructor<?> constructor = type.getConstructor(Context.class);
            unityPlayer = constructor.newInstance(this);
            setContentView((View) unityPlayer);
            callUnity("requestFocus");
            if (resumed) callUnity("resume");
            if (focused) callUnity("windowFocusChanged", new Class<?>[] { boolean.class }, true);
        } catch (Exception failure) {
            startupFailure = failure;
            failureStage = "unity_player";
            showGate("Unity player is unavailable in this package.", true);
        }
    }

    private void callUnity(String name, Class<?>[] types, Object... args) {
        if (unityPlayer == null) return;
        try { unityPlayer.getClass().getMethod(name, types).invoke(unityPlayer, args); }
        catch (ReflectiveOperationException ignored) { }
    }
    private void callUnity(String name) { callUnity(name, new Class<?>[0]); }
    private boolean injectUnityEvent(InputEvent event) {
        if (unityPlayer == null) return false;
        try { return (Boolean) unityPlayer.getClass().getMethod("injectEvent", InputEvent.class).invoke(unityPlayer, event); }
        catch (ReflectiveOperationException ignored) { return false; }
    }

    @Override protected void onResume() { super.onResume(); resumed = true; callUnity("resume"); }
    @Override protected void onPause() { resumed = false; callUnity("pause"); super.onPause(); }
    @Override public void onWindowFocusChanged(boolean hasFocus) { super.onWindowFocusChanged(hasFocus); focused = hasFocus; callUnity("windowFocusChanged", new Class<?>[] { boolean.class }, hasFocus); }
    @Override public void onConfigurationChanged(Configuration config) { super.onConfigurationChanged(config); callUnity("configurationChanged", new Class<?>[] { Configuration.class }, config); }
    @Override public void onLowMemory() { super.onLowMemory(); callUnity("lowMemory"); }
    @Override protected void onNewIntent(Intent intent) { super.onNewIntent(intent); setIntent(intent); callUnity("newIntent", new Class<?>[] { Intent.class }, intent); }
    @Override public boolean dispatchKeyEvent(android.view.KeyEvent event) {
        return event.getAction() == android.view.KeyEvent.ACTION_MULTIPLE
                ? injectUnityEvent(event) : super.dispatchKeyEvent(event);
    }
    @Override public boolean onKeyUp(int keyCode, android.view.KeyEvent event) {
        return injectUnityEvent(event) || super.onKeyUp(keyCode, event);
    }
    @Override public boolean onTouchEvent(android.view.MotionEvent event) { return injectUnityEvent(event) || super.onTouchEvent(event); }
    @Override public boolean dispatchGenericMotionEvent(android.view.MotionEvent event) { return injectUnityEvent(event) || super.dispatchGenericMotionEvent(event); }
    @Override protected void onDestroy() { destroyed = true; callUnity("quit"); unityPlayer = null; super.onDestroy(); }

    private static Throwable unwrap(Throwable failure) {
        Throwable current = failure;
        while (current.getCause() != null && current.getCause() != current) current = current.getCause();
        return current;
    }

    private static final class StartupException extends RuntimeException {
        StartupException(String stage, Throwable cause) {
            super(stage, cause);
        }
    }
}
