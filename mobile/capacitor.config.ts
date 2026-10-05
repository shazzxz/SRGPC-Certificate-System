import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "in.srgpc.certificates",
  appName: "SRGPC Certificates",
  webDir: "www",
  server: {
    url: "https://srgpc-certificate-system.onrender.com",
    cleartext: false,
    androidScheme: "https"
  },
  android: {
    backgroundColor: "#102a43"
  }
};

export default config;
