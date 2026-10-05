package in.srgpc.certificates;

import android.Manifest;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.URLUtil;
import android.webkit.WebView;
import androidx.core.app.ActivityCompat;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    private static final int REQUEST_NOTIFICATIONS = 1101;
    private static final int REQUEST_STORAGE = 1102;
    private String pendingDownloadUrl;
    private String pendingDownloadUserAgent;
    private String pendingDownloadContentDisposition;
    private String pendingDownloadMimeType;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WebView webView = getBridge().getWebView();
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String userAgent, String contentDisposition, String mimeType, long contentLength) {
                pendingDownloadUrl = url;
                pendingDownloadUserAgent = userAgent;
                pendingDownloadContentDisposition = contentDisposition;
                pendingDownloadMimeType = mimeType;
                if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.P &&
                    ActivityCompat.checkSelfPermission(MainActivity.this, Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
                    ActivityCompat.requestPermissions(MainActivity.this,
                        new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, REQUEST_STORAGE);
                    return;
                }
                enqueueDownload();
            }
        });
        handleIntent(getIntent());
        requestNotificationPermission();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    private void enqueueDownload() {
        if (pendingDownloadUrl == null) return;
        String cookie = CookieManager.getInstance().getCookie(pendingDownloadUrl);
        String fileName = URLUtil.guessFileName(
            pendingDownloadUrl, pendingDownloadContentDisposition,
            pendingDownloadMimeType != null ? pendingDownloadMimeType : "application/pdf"
        );
        DownloadManager.Request request = new DownloadManager.Request(Uri.parse(pendingDownloadUrl));
        request.setTitle(fileName);
        request.setDescription("SRGPC certificate PDF");
        request.setMimeType(pendingDownloadMimeType != null ? pendingDownloadMimeType : "application/pdf");
        request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
        request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName);
        if (cookie != null) request.addRequestHeader("Cookie", cookie);
        if (pendingDownloadUserAgent != null) request.addRequestHeader("User-Agent", pendingDownloadUserAgent);
        DownloadManager manager = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
        manager.enqueue(request);
        pendingDownloadUrl = null;
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ActivityCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this,
                new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQUEST_NOTIFICATIONS);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_STORAGE && grantResults.length > 0 &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            enqueueDownload();
        }
    }

    private void handleIntent(Intent intent) {
        if (intent == null || intent.getData() == null) return;
        Uri data = intent.getData();
        if ("srgpc".equalsIgnoreCase(data.getScheme()) &&
            "oauth2callback".equalsIgnoreCase(data.getHost())) {
            String token = data.getQueryParameter("token");
            if (token != null && !token.isEmpty()) {
                getBridge().getWebView().loadUrl(
                    "https://srgpc-certificate-system.onrender.com/auth/mobile/complete?token=" + Uri.encode(token)
                );
            }
        }
    }
}
