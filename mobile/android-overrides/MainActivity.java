package in.srgpc.certificates;

import android.Manifest;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.Environment;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.core.app.ActivityCompat;
import androidx.credentials.Credential;
import androidx.credentials.CredentialManager;
import androidx.credentials.CustomCredential;
import androidx.credentials.GetCredentialRequest;
import androidx.credentials.GetCredentialResponse;
import androidx.credentials.CredentialManagerCallback;
import androidx.credentials.exceptions.GetCredentialException;

import com.getcapacitor.BridgeActivity;
import com.google.android.libraries.identity.googleid.GetGoogleIdOption;
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginHandle;
import ee.forgr.capacitor.social.login.GoogleProvider;
import ee.forgr.capacitor.social.login.ModifiedMainActivityForSocialLoginPlugin;
import ee.forgr.capacitor.social.login.SocialLoginPlugin;

import org.json.JSONObject;

import java.util.concurrent.Executor;
import java.util.concurrent.Executors;

public class MainActivity extends BridgeActivity implements ModifiedMainActivityForSocialLoginPlugin {
    private static final int REQUEST_NOTIFICATIONS = 1101;
    private static final int REQUEST_STORAGE = 1102;
    private static final String APP_HOST = "srgpc-certificate-system.onrender.com";

    private String pendingDownloadUrl;
    private String pendingDownloadUserAgent;
    private String pendingDownloadContentDisposition;
    private String pendingDownloadMimeType;

    private CredentialManager credentialManager;
    private final Executor googleExecutor = Executors.newSingleThreadExecutor();

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WebView webView = getBridge().getWebView();
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);

        // The app loads our own SRGPC site, so expose only the small native
        // Google sign-in bridge needed by that site.
        webView.addJavascriptInterface(new GoogleBridge(), "SRGPCNativeGoogle");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                if (url == null) return false;
                Uri uri = Uri.parse(url);
                if ("srgpc".equalsIgnoreCase(uri.getScheme())) {
                    handleIntent(new Intent(Intent.ACTION_VIEW, uri));
                    return true;
                }
                if ("http".equalsIgnoreCase(uri.getScheme()) ||
                    "https".equalsIgnoreCase(uri.getScheme())) {
                    String host = uri.getHost();
                    if (host != null && APP_HOST.equalsIgnoreCase(host)) return false;
                    // Keep third-party pages out of the WebView/native bridge.
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, uri));
                    } catch (Exception ignored) {}
                    return true;
                }
                return false;
            }
        });

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

        credentialManager = CredentialManager.create(this);
        handleIntent(getIntent());
        requestNotificationPermission();
    }

    @Override
    public void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode >= GoogleProvider.REQUEST_AUTHORIZE_GOOGLE_MIN &&
            requestCode < GoogleProvider.REQUEST_AUTHORIZE_GOOGLE_MAX) {
            PluginHandle pluginHandle = getBridge().getPlugin("SocialLogin");
            if (pluginHandle == null) return;
            Plugin plugin = pluginHandle.getInstance();
            if (plugin instanceof SocialLoginPlugin) {
                ((SocialLoginPlugin) plugin).handleGoogleLoginIntent(requestCode, data);
            }
        }
    }

    @Override
    public void IHaveModifiedTheMainActivityForTheUseWithSocialLoginPlugin() {}

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    private class GoogleBridge {
        @JavascriptInterface
        public void signIn(String webClientId) {
            if (webClientId == null || webClientId.trim().isEmpty()) {
                sendGoogleResult(null, "Google Sign-In is not configured.");
                return;
            }
            runOnUiThread(() -> requestGoogleCredential(webClientId.trim(), true));
        }
    }

    private void requestGoogleCredential(String webClientId, boolean authorizedOnly) {
        try {
            GetGoogleIdOption option = new GetGoogleIdOption.Builder()
                .setServerClientId(webClientId)
                .setFilterByAuthorizedAccounts(authorizedOnly)
                .setAutoSelectEnabled(authorizedOnly)
                .build();

            GetCredentialRequest request = new GetCredentialRequest.Builder()
                .addCredentialOption(option)
                .build();

            CancellationSignal cancellationSignal = new CancellationSignal();
            credentialManager.getCredentialAsync(
                this,
                request,
                cancellationSignal,
                googleExecutor,
                new CredentialManagerCallback<GetCredentialResponse, GetCredentialException>() {
                    @Override
                    public void onResult(GetCredentialResponse response) {
                        handleGoogleCredential(response);
                    }

                    @Override
                    public void onError(GetCredentialException e) {
                        if (authorizedOnly) {
                            runOnUiThread(() -> requestGoogleCredential(webClientId, false));
                        } else {
                            String message = e != null && e.getMessage() != null
                                ? e.getMessage()
                                : "No Google account credential was available.";
                            sendGoogleResult(null, message);
                        }
                    }
                }
            );
        } catch (Exception e) {
            if (authorizedOnly) {
                runOnUiThread(() -> requestGoogleCredential(webClientId, false));
            } else {
                sendGoogleResult(null, e.getMessage() != null ? e.getMessage() : "Google sign-in failed.");
            }
        }
    }

    private void handleGoogleCredential(GetCredentialResponse response) {
        try {
            Credential credential = response.getCredential();
            if (credential instanceof CustomCredential) {
                CustomCredential custom = (CustomCredential) credential;
                if (GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL.equals(custom.getType())) {
                    GoogleIdTokenCredential googleCredential =
                        GoogleIdTokenCredential.createFrom(custom.getData());
                    String idToken = googleCredential.getIdToken();
                    if (idToken != null && !idToken.isEmpty()) {
                        sendGoogleResult(idToken, null);
                        return;
                    }
                }
            }
            sendGoogleResult(null, "Google did not return an ID token.");
        } catch (Exception e) {
            sendGoogleResult(null, e.getMessage() != null ? e.getMessage() : "Could not read Google credential.");
        }
    }

    private void sendGoogleResult(String idToken, String error) {
        String tokenJson = idToken == null ? "null" : JSONObject.quote(idToken);
        String errorJson = error == null ? "null" : JSONObject.quote(error);
        String script = "window.__srgpcNativeGoogleResult && window.__srgpcNativeGoogleResult({idToken:"
            + tokenJson + ",error:" + errorJson + "});";
        runOnUiThread(() -> getBridge().getWebView().evaluateJavascript(script, null));
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
        Toast.makeText(this, "Certificate download started. Check Downloads.", Toast.LENGTH_SHORT).show();
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
                    "https://" + APP_HOST + "/auth/mobile/complete?token=" + Uri.encode(token)
                );
            }
        }
    }
}
