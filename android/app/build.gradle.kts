plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.devtools.ksp")
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

    buildTypes {
        debug {
            // Эмулятор: 10.0.2.2 → хост-машина. Реальное устройство: подставьте IP ПК в SERVER_WS_URL_DEVICE.
            buildConfigField("String", "SERVER_WS_URL", "\"ws://10.0.2.2:8000\"")
            // ПОЧЕМУ: adb reverse tcp:8000 tcp:8000 пробрасывает localhost телефона → localhost ПК
            buildConfigField("String", "SERVER_WS_URL_DEVICE", "\"ws://localhost:8000\"")
            // API key for server auth. Empty = auth disabled (dev mode).
            buildConfigField("String", "SERVER_API_KEY", "\"\"")
        }
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            // Заменить на реальный URL перед production
            buildConfigField("String", "SERVER_WS_URL", "\"wss://api.reflexio.example.com\"")
            buildConfigField("String", "SERVER_WS_URL_DEVICE", "\"wss://api.reflexio.example.com\"")
            buildConfigField("String", "SERVER_API_KEY", "\"\"")  // Set via CI/CD or local.properties
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
