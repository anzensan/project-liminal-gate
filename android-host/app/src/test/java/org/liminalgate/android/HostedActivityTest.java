package org.liminalgate.android;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/** The main-thread guard must be narrow: one error, and no other. */
public final class HostedActivityTest {
    @Test public void recognizesTheAndroid16ServiceConnectionOverload() {
        assertTrue(HostedActivity.isUnsupportedServiceConnection(new NoSuchMethodError(
            "public default void android.content.ServiceConnection.onServiceConnected("
                + "android.content.ComponentName,android.os.IBinder,android.app.IBinderSession)")));
    }

    @Test public void leavesEveryOtherMissingMethodAlone() {
        assertFalse(HostedActivity.isUnsupportedServiceConnection(
            new NoSuchMethodError("com.unity3d.player.UnityPlayer.<init>")));
        assertFalse(HostedActivity.isUnsupportedServiceConnection(
            new NoSuchMethodError("android.content.ServiceConnection.onServiceDisconnected")));
        assertFalse(HostedActivity.isUnsupportedServiceConnection(new NoSuchMethodError()));
    }
}
