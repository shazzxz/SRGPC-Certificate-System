from pathlib import Path

root = Path(__file__).resolve().parent
android = root / "android"
java_dir = android / "app/src/main/java/in/srgpc/certificates"
java_dir.mkdir(parents=True, exist_ok=True)
(java_dir / "MainActivity.java").write_text(Path(root / "android-overrides/MainActivity.java").read_text())

manifest = android / "app/src/main/AndroidManifest.xml"
text = manifest.read_text()
text = text.replace(
    '<manifest xmlns:android="http://schemas.android.com/apk/res/android">',
    '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
    '    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />\n'
    '    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" android:maxSdkVersion="28" />'
)
if 'android:scheme="srgpc"' not in text:
    needle = 'android:name=".MainActivity"'
    idx = text.find(needle)
    if idx < 0:
        raise RuntimeError("Generated Capacitor manifest does not contain MainActivity")
    start = text.rfind("<activity", 0, idx)
    end = text.find("</activity>", idx)
    block = text[start:end + len("</activity>")]
    block = block.replace(
        "</activity>",
        """<intent-filter>
            <action android:name="android.intent.action.VIEW" />
            <category android:name="android.intent.category.DEFAULT" />
            <category android:name="android.intent.category.BROWSABLE" />
            <data android:scheme="srgpc" android:host="oauth2callback" />
        </intent-filter>
    </activity>"""
    )
    text = text[:start] + block + text[end + len("</activity>"):]
manifest.write_text(text)
