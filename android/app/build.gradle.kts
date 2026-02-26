import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.devtools.ksp")
}

// ПОЧЕМУ local.properties: SERVER_WS_URL_DEVICE зависит от IP вашего ПК в сети.
// localhost:8000 работает только с adb reverse (USB кабель).
// WiFi — добавьте в local.properties (gitignored):
//   SERVER_WS_URL_DEVICE=ws://192.168.1.XXX:8000
val localProps = Properties().also { props ->
    val f = rootProject.file("local.properties")
    if (f.exists()) props.load(f.inputStream())
}

android {
    namespace = "com.reflexio.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.reflexio.app"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    // ПОЧЕМУ signingConfigs: Google Play требует подписанный AAB.
    // Ключи читаются из local.properties (gitignored) — никогда не коммитятся в репо.
    // Создать keystore: Build > Generate Signed Bundle/APK > Create new key
    signingConfigs {
        create("release") {
            storeFile = localProps.getProperty("KEYSTORE_PATH")?.let { file(it) }
            storePassword = localProps.getProperty("KEYSTORE_PASSWORD", "")
            keyAlias = localProps.getProperty("KEY_ALIAS", "reflexio")
            keyPassword = localProps.getProperty("KEY_PASSWORD", "")
        }
    }

    buildTypes {
        debug {
            // Эмулятор: 10.0.2.2 → хост-машина
            buildConfigField("String", "SERVER_WS_URL", "\"ws://10.0.2.2:8000\"")
            // Реальное устройство: читаем из local.properties (gitignored)
            //   USB + adb reverse → ws://localhost:8000 (default)
            //   WiFi             → ws://192.168.1.XXX:8000 (в local.properties)
            val deviceUrl = localProps.getProperty("SERVER_WS_URL_DEVICE", "ws://localhost:8000")
            buildConfigField("String", "SERVER_WS_URL_DEVICE", "\"$deviceUrl\"")
            // API key for server auth — читаем из local.properties (gitignored, безопасно).
            // Добавь в android/local.properties: SERVER_API_KEY=UKpOEPN9Tyv...
            val apiKey = localProps.getProperty("SERVER_API_KEY", "")
            buildConfigField("String", "SERVER_API_KEY", "\"$apiKey\"")
        }
        release {
            isMinifyEnabled = true  // Уменьшает размер APK ~30%, обфускация кода
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfig = signingConfigs.getByName("release")
            // Продакшн URL — заменить на реальный домен с SSL-сертификатом
            val prodUrl = localProps.getProperty("PROD_SERVER_URL", "wss://api.reflexio.example.com")
            buildConfigField("String", "SERVER_WS_URL", "\"$prodUrl\"")
            buildConfigField("String", "SERVER_WS_URL_DEVICE", "\"$prodUrl\"")
            val prodApiKey = localProps.getProperty("PROD_API_KEY", "")
            buildConfigField("String", "SERVER_API_KEY", "\"$prodApiKey\"")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14" // Совместимо с Kotlin 1.9.24
    }
}

dependencies {
    implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.24")
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.6.2")
    implementation("androidx.activity:activity-compose:1.8.1")
    implementation(platform("androidx.compose:compose-bom:2023.10.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.navigation:navigation-compose:2.7.7")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    ksp("androidx.room:room-compiler:2.6.1")

    implementation("androidx.work:work-runtime-ktx:2.9.0")

    // 2.0.10 собрана под Kotlin 2.2; 2.0.5 совместима с Kotlin 1.9
    implementation("com.github.gkonovalov.android-vad:webrtc:2.0.5")
}
