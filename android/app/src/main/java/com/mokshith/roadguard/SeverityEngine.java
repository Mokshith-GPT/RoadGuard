package com.mokshith.roadguard;

import android.graphics.Color;

/**
 * RoadGuard On-Device Severity Estimation Engine
 * Implements the Road Damage Severity Index (RDSI) and hazard tier mapping.
 */
public class SeverityEngine {

    public enum SeverityTier {
        LOW("Low", Color.parseColor("#10B981")),
        MEDIUM("Medium", Color.parseColor("#F59E0B")),
        HIGH("High", Color.parseColor("#EF4444")),
        OPTIMAL("Optimal", Color.parseColor("#3B82F6"));

        public final String label;
        public final int color;

        SeverityTier(String label, int color) {
            this.label = label;
            this.color = color;
        }
    }

    /**
     * Computes the road condition severity tier based on damaged pixel percentage
     * and presence of critical hazard entities (e.g. D40 Potholes).
     */
    public static SeverityTier evaluate(double damageAreaPct, boolean hasPothole, int totalDefects) {
        if (totalDefects == 0 || damageAreaPct <= 0.05) {
            return SeverityTier.OPTIMAL;
        }

        if (damageAreaPct > 15.0 || (hasPothole && damageAreaPct > 4.0)) {
            return SeverityTier.HIGH;
        } else if (damageAreaPct > 3.0 || hasPothole) {
            return SeverityTier.MEDIUM;
        } else {
            return SeverityTier.LOW;
        }
    }
}
