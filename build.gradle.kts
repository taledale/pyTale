/**
 * NOTE: This is entirely optional and basics can be done in `settings.gradle.kts`
 */

repositories {
    // Any external repositories besides: MavenLocal, MavenCentral, HytaleMaven, and CurseMaven
}

dependencies {
    implementation("org.graalvm.polyglot:polyglot:25.0.3")
    implementation("org.graalvm.polyglot:python-community:25.0.3")
    implementation("org.graalvm.python:python-embedding:25.0.3")
}