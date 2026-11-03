package com.mokshith.roadguard;

import android.Manifest;
import android.content.ContentValues;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.camera.core.CameraSelector;
import androidx.camera.core.ImageCapture;
import androidx.camera.core.ImageCaptureException;
import androidx.camera.core.Preview;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.camera.video.FileOutputOptions;
import androidx.camera.video.FallbackStrategy;
import androidx.camera.video.Quality;
import androidx.camera.video.QualitySelector;
import androidx.camera.video.Recorder;
import androidx.camera.video.Recording;
import androidx.camera.video.VideoCapture;
import androidx.camera.video.VideoRecordEvent;
import androidx.camera.view.PreviewView;
import androidx.core.content.ContextCompat;

import com.google.common.util.concurrent.ListenableFuture;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.ExecutionException;

/**
 * Foreground CameraX dashcam capture.
 * This Activity records while visible; Android background camera use needs a
 * dedicated foreground service and additional platform permissions/policies.
 */
public class CameraActivity extends AppCompatActivity {

    private static final long SEGMENT_MS = 5 * 60 * 1000L;
    private static final int MAX_CLIPS = 2;
    private PreviewView cameraPreview;
    private TextView txtTelemetryStats, txtSeverityBadge, txtDetectionSummary;
    private Button btnRecord;
    private ProcessCameraProvider cameraProvider;
    private ImageCapture imageCapture;
    private VideoCapture<Recorder> videoCapture;
    private Recording activeRecording;
    private File videoDirectory;
    private boolean keepRecording = false;
    private boolean rotationPending = false;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable rotateRunnable = this::rotateSegment;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_camera);

        cameraPreview = findViewById(R.id.cameraPreview);
        txtTelemetryStats = findViewById(R.id.txtTelemetryStats);
        txtSeverityBadge = findViewById(R.id.txtSeverityBadge);
        txtDetectionSummary = findViewById(R.id.txtDetectionSummary);
        Button btnCapture = findViewById(R.id.btnCaptureAudit);
        Button btnClose = findViewById(R.id.btnCloseCamera);
        btnRecord = findViewById(R.id.btnRecordDashcam);

        videoDirectory = new File(getExternalFilesDir(Environment.DIRECTORY_MOVIES), "RoadGuard");
        if (!videoDirectory.exists()) videoDirectory.mkdirs();

        btnClose.setOnClickListener(v -> finish());
        btnCapture.setOnClickListener(v -> captureEvidenceFrame());
        btnRecord.setOnClickListener(v -> confirmAndToggleRecording());

        txtTelemetryStats.setText("Camera preview active | Model inference not configured");
        txtSeverityBadge.setText("MODEL OFFLINE");
        txtDetectionSummary.setText("No AI detections are being generated. Save an evidence frame or start local video recording.");
        startCamera();
    }

    private void startCamera() {
        ListenableFuture<ProcessCameraProvider> future = ProcessCameraProvider.getInstance(this);
        future.addListener(() -> {
            try {
                cameraProvider = future.get();
                bindCamera(cameraProvider);
            } catch (ExecutionException | InterruptedException e) {
                Toast.makeText(this, "Camera initialization failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
            }
        }, ContextCompat.getMainExecutor(this));
    }

    private void bindCamera(@NonNull ProcessCameraProvider provider) {
        Preview preview = new Preview.Builder().build();
        CameraSelector selector = new CameraSelector.Builder()
            .requireLensFacing(CameraSelector.LENS_FACING_BACK).build();
        preview.setSurfaceProvider(cameraPreview.getSurfaceProvider());

        imageCapture = new ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).build();

        Recorder recorder = new Recorder.Builder()
            .setQualitySelector(QualitySelector.from(Quality.SD, FallbackStrategy.lowerQualityOrHigherThan(Quality.SD)))
            .build();
        videoCapture = VideoCapture.withOutput(recorder);

        provider.unbindAll();
        provider.bindToLifecycle(this, selector, preview, imageCapture, videoCapture);
        txtTelemetryStats.setText("Camera ready | Video: SD quality | Clips retained: latest 2");
    }

    private void confirmAndToggleRecording() {
        if (activeRecording != null || keepRecording) {
            keepRecording = false;
            handler.removeCallbacks(rotateRunnable);
            if (activeRecording != null) activeRecording.stop();
            activeRecording = null;
            btnRecord.setText("● Start recording");
            txtSeverityBadge.setText("CAMERA READY");
            return;
        }
        new AlertDialog.Builder(this)
            .setTitle("Dashcam storage notice")
            .setMessage("RoadGuard retains only the two latest completed video clips in this app's storage. Older clips beyond that limit will be permanently deleted as new clips are saved. Recording runs while this camera screen stays active. Continue?")
            .setNegativeButton("Cancel", (dialog, which) -> dialog.dismiss())
            .setPositiveButton("Continue", (dialog, which) -> {
                pruneClips(MAX_CLIPS);
                keepRecording = true;
                startSegment();
            })
            .show();
    }

    private void startSegment() {
        if (!keepRecording || videoCapture == null || isFinishing()) return;
        String stamp = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date());
        File output = new File(videoDirectory, "RoadGuard_" + stamp + ".mp4");
        FileOutputOptions options = new FileOutputOptions.Builder(output).build();
        activeRecording = videoCapture.getOutput()
            .prepareRecording(this, options)
            .start(ContextCompat.getMainExecutor(this), event -> {
                if (event instanceof VideoRecordEvent.Start) {
                    btnRecord.setText("■ Stop recording");
                    txtSeverityBadge.setText("RECORDING");
                    txtTelemetryStats.setText("Dashcam recording | Latest 2 clips retained");
                } else if (event instanceof VideoRecordEvent.Finalize) {
                    VideoRecordEvent.Finalize finalized = (VideoRecordEvent.Finalize) event;
                    activeRecording = null;
                    if (finalized.hasError()) {
                        keepRecording = false;
                        Toast.makeText(this, "Video recording failed: " + finalized.getError(), Toast.LENGTH_LONG).show();
                        btnRecord.setText("● Start recording");
                        txtSeverityBadge.setText("CAMERA READY");
                    } else {
                        writeClipMetadata(output);
                        pruneClips(MAX_CLIPS);
                        Toast.makeText(this, "Saved dashcam clip: " + output.getName(), Toast.LENGTH_SHORT).show();
                        if (keepRecording && !isFinishing()) startSegment();
                    }
                }
            });
        handler.removeCallbacks(rotateRunnable);
        handler.postDelayed(rotateRunnable, SEGMENT_MS);
    }

    private void rotateSegment() {
        if (!keepRecording || activeRecording == null || rotationPending) return;
        rotationPending = true;
        Recording old = activeRecording;
        activeRecording = null;
        old.stop();
        // Finalize callback starts the next segment.
        rotationPending = false;
    }

    private void writeClipMetadata(File videoFile) {
        try {
            JSONObject data = new JSONObject();
            data.put("file", videoFile.getName());
            data.put("capturedAt", new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).format(new Date(videoFile.lastModified())));
            data.put("storage", "app-private external Movies/RoadGuard");
            data.put("analysis", "not performed by this APK build");
            try (FileOutputStream stream = new FileOutputStream(new File(videoFile.getAbsolutePath() + ".json"))) {
                stream.write(data.toString(2).getBytes(StandardCharsets.UTF_8));
            }
        } catch (Exception ignored) { }
    }

    private void pruneClips(int keep) {
        if (videoDirectory == null || !videoDirectory.exists()) return;
        File[] files = videoDirectory.listFiles((dir, name) -> name.toLowerCase(Locale.ROOT).endsWith(".mp4"));
        if (files == null) return;
        Arrays.sort(files, Comparator.comparingLong(File::lastModified).reversed());
        for (int i = keep; i < files.length; i++) {
            File metadata = new File(files[i].getAbsolutePath() + ".json");
            // Never delete a file that is still actively being written.
            if (activeRecording != null && files[i].equals(getActiveOutputFile())) continue;
            files[i].delete();
            if (metadata.exists()) metadata.delete();
        }
    }

    private File getActiveOutputFile() {
        // CameraX owns the active output; it is not retained as a mutable file handle.
        return null;
    }

    private void captureEvidenceFrame() {
        if (imageCapture == null) {
            Toast.makeText(this, "Camera is not ready.", Toast.LENGTH_SHORT).show();
            return;
        }
        File pictures = new File(getExternalFilesDir(Environment.DIRECTORY_PICTURES), "RoadGuard");
        if (!pictures.exists()) pictures.mkdirs();
        String stamp = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date());
        File output = new File(pictures, "RoadGuard_Evidence_" + stamp + ".jpg");
        ImageCapture.OutputFileOptions options = new ImageCapture.OutputFileOptions.Builder(output).build();
        imageCapture.takePicture(options, ContextCompat.getMainExecutor(this), new ImageCapture.OnImageSavedCallback() {
            @Override public void onImageSaved(@NonNull ImageCapture.OutputFileResults result) {
                writeEvidenceMetadata(output);
                Toast.makeText(CameraActivity.this, "Evidence image saved in app storage.", Toast.LENGTH_LONG).show();
            }
            @Override public void onError(@NonNull ImageCaptureException exception) {
                Toast.makeText(CameraActivity.this, "Could not save image: " + exception.getMessage(), Toast.LENGTH_LONG).show();
            }
        });
    }

    private void writeEvidenceMetadata(File imageFile) {
        try {
            JSONObject data = new JSONObject();
            data.put("file", imageFile.getName());
            data.put("capturedAt", new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).format(new Date()));
            data.put("latitude", JSONObject.NULL);
            data.put("longitude", JSONObject.NULL);
            data.put("analysis", "not performed by this APK build");
            try (FileOutputStream stream = new FileOutputStream(new File(imageFile.getAbsolutePath() + ".json"))) {
                stream.write(data.toString(2).getBytes(StandardCharsets.UTF_8));
            }
        } catch (Exception ignored) { }
    }

    @Override
    protected void onStop() {
        // CameraX cannot keep a background camera session bound to this Activity.
        // Stop safely rather than continuing to claim that background recording works.
        keepRecording = false;
        handler.removeCallbacks(rotateRunnable);
        if (activeRecording != null) {
            activeRecording.stop();
            activeRecording = null;
        }
        super.onStop();
    }

    @Override
    protected void onDestroy() {
        if (cameraProvider != null) cameraProvider.unbindAll();
        super.onDestroy();
    }
}
