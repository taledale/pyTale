/**
 * NOTE: This is entirely optional and basics can be done in `settings.gradle.kts`
 */

repositories {
    // Any external repositories besides: MavenLocal, MavenCentral, HytaleMaven, and CurseMaven
}

dependencies {
    implementation("org.graalvm.polyglot:polyglot:24.2.1")
    implementation("org.graalvm.polyglot:python-community:24.2.1")
}

tasks.register("generateClasspath") {
    doLast {
        val classpath = configurations.runtimeClasspath.get().asPath
        val resourceDir = file("build/resources/main/META-INF")
        resourceDir.mkdirs()
        file("build/resources/main/META-INF/javac-classpath.txt").writeText(classpath)
        println("✓ Classpath saved to: build/resources/main/META-INF/javac-classpath.txt")
    }
}

tasks.named("processResources") {
    dependsOn("generateClasspath")
}
