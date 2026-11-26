package com.wraith.agent;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.text.SpannableString;
import android.text.style.ForegroundColorSpan;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.LinkedList;
import java.util.List;

public class MainActivity extends Activity {
    private static final int BG = 0xFF080D12;
    private static final int FG = 0xFFE6F1F5;
    private static final int ACCENT = 0xFF21E6A1;

    private EditText objective;
    private EditText scope;
    private Switch dryRun;
    private TextView logView;
    private TextView statusView;
    private ScrollView scroll;
    private File logFile;
    private final Handler handler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        logFile = new File(getFilesDir(), "wraith.log");

        File scopeFile = new File(getFilesDir(), "scope.yaml");
        if (!scopeFile.exists()) {
            try {
                Files.write(scopeFile.toPath(), "allowed:\n  - 192.168.0.0/24\n".getBytes(StandardCharsets.UTF_8));
            } catch (Exception ignored) {
            }
        }

        if (Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 7);
        }

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);
        int pad = dp(20);
        root.setPadding(pad, dp(32), pad, pad);

        TextView title = label("WRAITH", 26, ACCENT);
        title.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
        root.addView(title);

        TextView sub = label("scope-locked agent  |  rooted NetHunter  |  no Termux", 12, 0xFF7B909A);
        sub.setPadding(0, dp(2), 0, dp(16));
        root.addView(sub);

        root.addView(label("OBJECTIVE", 12, ACCENT));
        objective = new EditText(this);
        objective.setText("quick web scan");
        objective.setSingleLine(true);
        objective.setTextColor(FG);
        objective.setHintTextColor(0xFF60727C);
        root.addView(field(objective));

        root.addView(label("SCOPE (allowed IPs / CIDRs)", 12, ACCENT));
        scope = new EditText(this);
        scope.setText("allowed:\n  - 192.168.0.0/24");
        scope.setLines(3);
        scope.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        scope.setTypeface(Typeface.MONOSPACE);
        scope.setTextColor(FG);
        root.addView(field(scope));

        dryRun = new Switch(this);
        dryRun.setText("DRY-RUN  (preview only, nothing executes)");
        dryRun.setTextColor(FG);
        dryRun.setChecked(true);
        LinearLayout.LayoutParams dryParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        dryParams.setMargins(0, dp(10), 0, dp(10));
        root.addView(dryRun, dryParams);

        LinearLayout buttons = new LinearLayout(this);
        buttons.setOrientation(LinearLayout.HORIZONTAL);
        Button start = button("START");
        Button stop = button("STOP");
        buttons.addView(start, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        buttons.addView(stop, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        root.addView(buttons);

        statusView = label("● IDLE", 13, 0xFF7B909A);
        statusView.setPadding(0, dp(12), 0, dp(6));
        root.addView(statusView);

        scroll = new ScrollView(this);
        scroll.setBackgroundColor(0xFF0D151B);
        logView = new TextView(this);
        logView.setTypeface(Typeface.MONOSPACE);
        logView.setTextSize(12);
        logView.setTextColor(0xFFB8D2DA);
        logView.setText("waiting for agent...\n");
        scroll.addView(logView, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));
        root.addView(scroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));

        start.setOnClickListener(v -> {
            try {
                Files.write(scopeFile.toPath(), scope.getText().toString().getBytes(StandardCharsets.UTF_8));
                if (logFile.exists() && !logFile.delete()) {
                    // keep the old log if deletion is not permitted
                }
            } catch (Exception e) {
                Toast.makeText(this, "Cannot save scope: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                return;
            }
            logView.setText("starting...\n");
            Intent intent = new Intent(this, WraithService.class);
            intent.putExtra("objective", objective.getText().toString());
            intent.putExtra("dry", dryRun.isChecked());
            startForegroundService(intent);
            Toast.makeText(this, dryRun.isChecked() ? "Dry-run started" : "Agent started", Toast.LENGTH_SHORT).show();
        });

        stop.setOnClickListener(v -> {
            stopService(new Intent(this, WraithService.class));
            WraithService.running = false;
            Toast.makeText(this, "Stop signal sent", Toast.LENGTH_SHORT).show();
        });

        setContentView(root);
        handler.postDelayed(poll, 500);
    }

    private final Runnable poll = new Runnable() {
        @Override
        public void run() {
            List<String> lines = tail(logFile, 250);
            if (!lines.isEmpty()) {
                SpannableString text = new SpannableString(String.join("\n", lines));
                int offset = 0;
                for (String line : lines) {
                    int color = 0xFFB8D2DA;
                    if (line.startsWith("[SUCCESS]")) {
                        color = ACCENT;
                    } else if (line.startsWith("[OUT]")) {
                        color = 0xFF8FB6C2;
                    }
                    text.setSpan(new ForegroundColorSpan(color), offset,
                            offset + line.length(), 0);
                    offset += line.length() + 1;
                }
                logView.setText(text);
                scroll.post(() -> scroll.fullScroll(ScrollView.FOCUS_DOWN));
            }
            statusView.setText(WraithService.running ? "● RUNNING" : "● IDLE");
            statusView.setTextColor(WraithService.running ? ACCENT : 0xFF7B909A);
            handler.postDelayed(this, 200);
        }
    };

    @Override
    protected void onDestroy() {
        handler.removeCallbacks(poll);
        super.onDestroy();
    }

    private TextView label(String text, int size, int color) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setTypeface(Typeface.MONOSPACE);
        return view;
    }

    private LinearLayout field(EditText editText) {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setBackgroundColor(0xFF0D151B);
        wrap.setPadding(dp(12), dp(8), dp(12), dp(8));
        wrap.addView(editText, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));
        return wrap;
    }

    private Button button(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(0xFF04120D);
        button.setBackgroundColor(ACCENT);
        button.setAllCaps(true);
        return button;
    }

    private static List<String> tail(File file, int max) {
        LinkedList<String> lines = new LinkedList<>();
        if (!file.exists()) {
            return lines;
        }
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = reader.readLine()) != null) {
                lines.add(line);
                if (lines.size() > max) {
                    lines.removeFirst();
                }
            }
        } catch (Exception ignored) {
        }
        return lines;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density);
    }
}
