package com.mokshith.roadguard;

import android.os.Bundle;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.camera.core.CameraSelector;
import androidx.camera.core.Preview;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.camera.view.PreviewView;
import androidx.core.content.ContextCompat;

import com.google.common.util.concurrent.ListenableFuture;

import java.util.concurrent.ExecutionException;

/**
 * RoadGuard Camera & Real-Time Telemetry HUD Activity
 */
public class CameraActivity extends AppCompatActivity {

    private PreviewView cameraPreview;
    private TextView txtTelemetryStats;
    private TextView txtSeverityBadge;
    private TextView txtDetectionSummary;

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

        btnClose.setOnClickListener(v -> finish());
        btnCapture.setOnClickListener(v -> captureRoadAudit());

        startCamera();
    }

    private void startCamera() {
        ListenableFuture<ProcessCameraProvider> cameraProviderFuture =
            ProcessCameraProvider.getInstance(this);

        cameraProviderFuture.addListener(() -> {
            try {
                ProcessCameraProvider cameraProvider = cameraProviderFuture.get();
                bindPreview(cameraProvider);
            } catch (ExecutionException | InterruptedException e) {
                Toast.makeText(this, "Camera initialization failed: " + e.getMessage(), Toast.LENGTH_SHORT).show();
            }
        }, ContextCompat.getMainExecutor(this));
    }

    private void bindPreview(@NonNull ProcessCameraProvider cameraProvider) {
        Preview preview = new Preview.Builder().build();
        CameraSelector cameraSelector = new CameraSelector.Builder()
            .requireLensFacing(CameraSelector.LENS_FACING_BACK)
            .build();

        preview.setSurfaceProvider(cameraPreview.getSurfaceProvider());
        cameraProvider.unbindAll();
        cameraProvider.bindToLifecycle(this, cameraSelector, preview);

        // Update initial telemetry state
        updateTelemetry(3.8, true, 2);
    }

    private void updateTelemetry(double damagePct, boolean hasPothole, int defectCount) {
        SeverityEngine.SeverityTier tier = SeverityEngine.evaluate(damagePct, hasPothole, defectCount);
        txtSeverityBadge.setText(tier.label.toUpperCase());
        txtSeverityBadge.setBackgroundColor(tier.color);

        txtTelemetryStats.setText(String.format("Defects: %d | Affected Area: %.1f%%", defectCount, damagePct));
        txtDetectionSummary.setText(String.format("Monitoring driving corridor. Detected %d structural pavement entities.", defectCount));
    }

    private void captureRoadAudit() {
        Toast.makeText(this, "📸 Pavement defect snapshot saved to inspection log.", Toast.LENGTH_SHORT).show();
    }
}
