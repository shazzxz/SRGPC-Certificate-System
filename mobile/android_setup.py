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
    if 'android:launchMode="singleTask"' not in block:
        block = block.replace('android:name=".MainActivity"', 'android:name=".MainActivity"\n            android:launchMode="singleTask"')
    text = text[:start] + block + text[end + len("</activity>"):]
manifest.write_text(text)

# The current Social Login Android dependency uses androidx.browser 1.9.x,
# which requires Android API 36 and AGP 8.9.1+. Capacitor 7.4.4 still
# generates a project using AGP 8.7.2 / compileSdk 35, so upgrade only the
# generated Android build settings here rather than changing the app runtime
# target SDK.
variables = android / "variables.gradle"
if variables.exists():
    v = variables.read_text()
    v = v.replace("compileSdkVersion = 35", "compileSdkVersion = 36")
    v = v.replace("minSdkVersion = 23", "minSdkVersion = 24")
    variables.write_text(v)

# Native Google Sign-In uses Android Credential Manager directly. These libraries are
# not pulled in by the web Capacitor bundle, so declare them in the generated app
# module before compiling MainActivity.java.
app_gradle = android / "app/build.gradle"
if app_gradle.exists():
    a = app_gradle.read_text()
    deps = '''\n    implementation "androidx.credentials:credentials:1.6.0"\n    implementation "androidx.credentials:credentials-play-services-auth:1.6.0"\n    implementation "com.google.android.libraries.identity.googleid:googleid:1.2.1"\n'''
    if 'androidx.credentials:credentials:1.6.0' not in a:
        marker = "dependencies {"
        if marker not in a:
            raise RuntimeError("Generated app build.gradle does not contain dependencies block")
        a = a.replace(marker, marker + deps, 1)
        app_gradle.write_text(a)

root_gradle = android / "build.gradle"
if root_gradle.exists():
    g = root_gradle.read_text()
    g = g.replace("com.android.tools.build:gradle:8.7.2", "com.android.tools.build:gradle:8.9.1")
    root_gradle.write_text(g)
