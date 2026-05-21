// build.gradle.kts — Vedix Research Workbench plugin for the IntelliJ Platform.
//
// This build is driven by the IntelliJ Platform Gradle Plugin 2.0+, which
// replaces the legacy `gradle-intellij-plugin`. We target IntelliJ IDEA
// Community 2024.2.1 as the build base, which is API-compatible with
// PyCharm, CLion, WebStorm, and the other JetBrains IDEs we care about.

plugins {
    java
    id("org.jetbrains.kotlin.jvm") version "1.9.25"
    id("org.jetbrains.intellij.platform") version "2.0.1"
}

group = "ai.vedix"
version = "3.0.0"

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    intellijPlatform {
        intellijIdeaCommunity("2024.2.1")
        bundledPlugin("com.intellij.java")
        instrumentationTools()
        testFramework(org.jetbrains.intellij.platform.gradle.TestFrameworkType.Platform)
    }
    implementation("com.google.code.gson:gson:2.10.1")
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

kotlin {
    jvmToolchain(17)
}

tasks.test {
    useJUnitPlatform()
}

intellijPlatform {
    pluginConfiguration {
        ideaVersion {
            sinceBuild.set("242")
            untilBuild.set("251.*")
        }
    }
}
