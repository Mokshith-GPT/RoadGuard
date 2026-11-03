package com.mokshith.roadguard;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

/**
 * RoadGuard Main Entry Activity
 */
public class MainActivity extends AppCompatActivity {

    private static final int PERMISSION_REQ_CODE = 101;
    private EditText editServerUrl;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        editServerUrl = findViewById(R.id.editServerUrl);
        Button btnStartLive = findViewById(R.id.btnStartLive);
        Button btnGallery = findViewById(R.id.btnGallery);

        btnStartLive.setOnClickListener(v -> checkPermissionsAndLaunchCamera());

        btnGallery.setOnClickListener(v -> {
            Toast.makeText(this, "Select an asphalt road photo to analyze severity.", Toast.LENGTH_SHORT).show();
            Intent intent = new Intent(Intent.ACTION_PICK);
            intent.setType("image/*");
            startActivity(intent);
        });
    }

    private void checkPermissionsAndLaunchCamera() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                this,
                new String[]{Manifest.permission.CAMERA, Manifest.permission.ACCESS_FINE_LOCATION},
                PERMISSION_REQ_CODE
            );
        } else {
            launchCamera();
        }
    }

    private void launchCamera() {
        Intent intent = new Intent(this, CameraActivity.class);
        intent.putExtra("SERVER_URL", editServerUrl.getText().toString().trim());
        startActivity(intent);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == PERMISSION_REQ_CODE) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                launchCamera();
            } else {
                Toast.makeText(this, R.string.camera_permission_required, Toast.LENGTH_LONG).show();
            }
        }
    }
}
