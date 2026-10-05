# SRGPC Android App

This directory contains the Capacitor shell for the SRGPC Certificate Management System.

The Android app opens the production SRGPC portal in a standalone native shell. The Flask application remains the single source of truth, so login, certificates, verification, student/admin portals and PDF generation continue to use the existing backend.

The GitHub Actions workflow builds a debug APK automatically. A signed release/AAB build can be added later for Play Store distribution once a release signing key is configured.
