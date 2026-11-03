# RoadGuard Privacy Policy

**Effective Date:** November 3, 2026  
**Developer:** Mokshith Y Nanda (`Mokshith-GPT`)

RoadGuard is an automated computer vision application designed to assist civil engineers, municipalities, and road inspection authorities in detecting pavement distress and estimating road surface damage severity.

---

### 1. Information Collection & Usage

#### A. Camera Access (`android.permission.CAMERA`)
* **Purpose:** The app accesses the device's camera exclusively to capture real-time road surface imagery for pavement damage inspection, crack segmentation, and pothole detection.
* **Storage:** Image frames are processed locally or against the user's configured RoadGuard inspection server. RoadGuard does not transmit or sell personal imagery to third-party advertising networks.

#### B. Location Information (`android.permission.ACCESS_FINE_LOCATION`)
* **Purpose:** When permitted by the user, location coordinates are tagged alongside detected road defects to record the geographic location of potholes and road cracks for audit reports.
* **Consent:** Location tagging is optional and can be toggled off within the application settings.

#### C. Network Access (`android.permission.INTERNET`)
* **Purpose:** Used strictly to synchronize inspection telemetry with the RoadGuard analysis server and download updated road condition inspection reports.

---

### 2. Google Play Protect & Security Compliance
* RoadGuard does not bundle any third-party ad networks, hidden background services, or tracking SDKs.
* The application complies with Google Play Target API 34 security requirements and adheres to sandboxed scoped storage models.

---

### 3. Contact & Open Source
For inquiries regarding source code or municipal deployment:
* **Repository:** [https://github.com/Mokshith-GPT/RoadGuard](https://github.com/Mokshith-GPT/RoadGuard)
* **License:** Apache License 2.0
