package com.wraith.agent;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileWriter;

public class WraithService extends Service {
    public static volatile boolean running = false;
    private static final String CHANNEL = "wraith";

    @Override
    public void onCreate() {
        super.onCreate();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL, "Wraith agent", NotificationManager.IMPORTANCE_LOW);
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(1001, notification());
        running = true;

        String objective = intent != null ? intent.getStringExtra("objective") : "quick web scan";
        boolean dry = intent == null || intent.getBooleanExtra("dry", true);

        File dir = getFilesDir();
        String scopePath = new File(dir, "scope.yaml").getAbsolutePath();
        String logPath = new File(dir, "wraith.log").getAbsolutePath();

        try {
            PyObject bridge = bridge();
            bridge.callAttr("configure", dir.getAbsolutePath(), scopePath, logPath);
            bridge.callAttr("run", objective, dry);
        } catch (Throwable t) {
            append(logPath, "[error] bridge start failed: " + t);
        }
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        try {
            bridge().callAttr("stop");
        } catch (Throwable ignored) {
        }
        stopForeground(true);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private PyObject bridge() {
        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(getApplicationContext()));
        }
        return Python.getInstance().getModule("wraith.bridge");
    }

    private Notification notification() {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pending = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL)
                : new Notification.Builder(this);
        return builder
                .setContentTitle("Wraith")
                .setContentText("Agent active — scope-locked")
                .setSmallIcon(android.R.drawable.ic_menu_compass)
                .setContentIntent(pending)
                .setOngoing(true)
                .build();
    }

    private static void append(String path, String line) {
        try (FileWriter writer = new FileWriter(path, true)) {
            writer.write(line.trim() + "\n");
        } catch (Exception ignored) {
        }
    }
}
