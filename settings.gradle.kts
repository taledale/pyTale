rootProject.name = "pytale"

plugins {
    // See documentation on https://scaffoldit.dev
    id("dev.scaffoldit") version "0.2.+"
}

// Would you like to do a split project?
// Create a folder named "common", then configure details with `common { }`

hytale {
    usePatchline("release")
    useVersion("0.5.4")

    dependencies {
        // Any external dependency you also want to include
    }

    manifest {
        Group = "TaleDale"
        Name = "PyTale"
        Main = "dev.taledale.pytale.PyTale"
        Version = "0.0.1"
        DisabledByDefault = false
        IncludesAssetPack = false
        ServerVersion = "=0.5.4"
    }
}
