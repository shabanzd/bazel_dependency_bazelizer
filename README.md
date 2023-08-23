# dependency-bazelizer (WIP)

The `dependency-bazelizer` takes an input list of debian packages, and turns them and their entire transitive dependency subgraphs into ready-to-use, fully bazelizer modules (bzlmods). It also automatically references the bazelized modules in the internal registry of the repo. A demo of how this looks like can be found at: <https://www.youtube.com/watch?v=69C_g4QO8xM&t=1s>

So far, the `dependency-bazelizer` supports debian packages only. The plan is to include Python as well in the following versions.

## Getting started

### Requirements

In order to try the `dependency-bazelizer`, you need a linux distribution running `apt` and `dpkg`. These are needed to manage and unpack the debian packages. In addition, `patchelf` needs to be installed (preferably version 0.10). The reason `patchelf` was not bazelized is that I don't know where this script will run (ubuntu, wsl ... etc). In case you are interested in bazelizing the `patchelf` dependency, you can easily do that using the `dependency-bazelizer` itself on your chosen platform. You are recommended to have [bazelisk](https://github.com/bazelbuild/bazelisk) installed as well.

The [Youtube Demo](<https://www.youtube.com/watch?v=69C_g4QO8xM&t=1s>) mentioned above, shows how to use the `depedenncy-bazelizer` as an interactive tool (the first part of the video), and as a module with an extension (the latter part of the video).

### Using the dependency-bazelizer as an interactive tool

In order to use the `dependency-bazelizer` as an interactive tool, and get to know its features, you will simply need to:

* clone the repo.
* `cd dependency_bazelizer`
* run the `dependency-bazelizer` and provide the [input file](#input-file) and the [config file](#config-file) as follows:
`bazelisk run //src:dependency-bazelizer -- -if /path/to/input_file.in -cf /path/to/storage_config.json`

### Using the dependency-bazelizer as bzlmod:

An example of this usage is provided in the [demo_module](https://github.com/shabanzd/dependency-bazelizer/tree/main/demo_module) directory.

What is needed to get started is the following:

* In the `MODULE.bazel`, add:
```
# since the dependency bazelizer is not in the BCR yet, downloading it and
# referring to it with local_path_override is currently the only option.
# This should be nicer once the dependency bazelizer is uploaded to the BCR.
bazel_dep(name = "dependency_bazelizer", version = "")
local_path_override(
    module_name = "dependency_bazelizer",
    path = "../dependency_bazelizer/",
)
dependency_bazelizer = use_extension("@dependency_bazelizer//:input.bzl", "dependency_bazelizer")
dependency_bazelizer.config(deb_packages_input_file = "//:input_file.in", storage_config_file = "//:storage_config.json")
use_repo(dependency_bazelizer, "dep_bazelizer_config")
```
where deb_packages_input_file and the storage_config_file of the config tag class expect an [input file](#input-file) and a [config file](#config-file) respectively.

* Add the following to the `BUILD` file:
```
load("@dependency_bazelizer//:run_bazelizer.bzl", "run_bazelizer")
run_bazelizer(repository = "@dep_bazelizer_config")
```
* call `bazelisk run //path/to/build/file:dependency-bazelizer`



### Input file
The input file is the file containing the debian packages to be turned into bzlmods. Similar to:

```
# The input deb package needs to follow the template: 
# name:arch=version. Where name and arch are mandatory, and version is optional.
deb_package1:amd64=1.2.3
deb_package2:amd64=1.2.3
```

### Config file
The storage config file must be written in compliance with one of the following schemas:

* For the `AWS S3` storage: 
```javascript
{
        "download_url": "https://mydownloadurl.com", // mandatory
        "storage": {
            "aws_s3": {
                "bucket": "mybucket", // mandatory
                "credentials_profile": "other-profile", // optional
                "upload_url": "https://pub-57066c0fbbb14beb942f046a28ab836b.r2.dev" // mandatory
            }
        }
}
```

* For the `unknown` storage, which means that the files tars are dumped somewhere and the user will take care of uploading them to the storage of their choice: 
```javascript
{
        "download_url": "https://mydownloadurl.com", // mandatory
        "storage": {
            "unknown": {
                "path": "mydir" // mandatory
            }
        }
}
```


## Summary

Up until `Bazel 5`, Bazel had not been able to resolve dependency graphs. As a result, Bazel needed a dependency manager to run during every build to build the transitive dependency graph of each dependency. Since this process needed to run early in the build, repository rules for package managers were developed and became the norm.

Since `Bazel 6` and the introduction of `bzlmod`s, the approach described above is no longer the only option.

The `dependency-bazelizer` is a tool that takes input packages of different types, then turns those packages, in addition to their entire dependency graphs, into `bzlmod`s and references them in an internal `registry`. The freshly generated `bzlmod`s are ready to be resolved and consumed directly by `Bazel`. This eliminates the need to have package managers running in repository rules in order to resolve dependency graphs for `Bazel`.

A bonus added feature, is that the modules access their transitive runtime dependencies directly from the runfiles; not from sysroot or a custom sysroot.

### What if every dependency was a bzlmod?

Imagine every debian dependency, every python dependency ... etc has suddenly become a bazel module. What would happen?

* Package managers running as repository rules would no longer be needed. Meaning that dependencies wouldn't need to be installed over and over again in the early stages of each uncached build => more efficient builds.

* Bazel would build a strict dependency subgraph for each dependency, and even provide a lock file representing these subgraphs => Easier and more reliable Software Bill Of Material (SBOM) for the modules.

* The input to actions are now `bzlmod`s representing individual debian/python dependencies, and not a third-party-package-manager lock file representing the entire debian/python dependency graph as one input. This allows for a more granual builds.

### How can we make that happen?

`Bzlmod` act cool, but in reality, they are anything with a `MODULE.bazel` file on top, and a few accessory files like an empty `WORKSPACE` and a `BUILD.bazel` file exposing the files and targets to be used by other modules.

So in order to turn a debian package, say `deb_a`, into a module, all we need to do is: unpackage it, put a `MODULE.bazel`, empty `WORKSPACE` and a `BUILD.bazel` file on top, and store the folder containing everything somewhere in the repo (or archive it and upload it somewhere).

Great, so now `deb_a` is a module. Problem is, it is likely that `deb_a` has transitive dependencies. In order for the `deb_a` module to fetch those dependencies, they also need to be modules. In other words, the entire subgraph needs to be built up of bazel modules. This means that the modularization process mentioned above should be done for the entire dependency subgraph.

The dependency-bazelizer tries to do exactly that; it processes the entire dependency graph and repackages it into modules. It also adds references to these modules in a local registry inside the repo. One can visualize the process as in the graph below

```mermaid
graph LR;
    A[Unpackage Dependency]-->B[Modularize Dependency];
    B-->C[Reference Dependency in The Local Registry];
    D[Next Dependency]-->A;
    C --> D;
```

Since it is not necessary for this tool to be implemented as a repository rule, I decided to do it entirely in python. This could make the code base easier to test and collaborate on.

## Nerdy details / Contributor zone

The work is not done by adding a `MODULE.bazel` to a package and making sure that this module fetches the needed transitive dependencies. The pre-compiled C/C++ files in a package don't only expect their transitive runtime dependencies to exist on the system, but also to exist in a specific predefined location (`/bin/` for example). However, we don't want the transitive dependencies to be accessed directly from the system, we want the transitive deps in the runfiles to be the ones used ! This makes the problem way more exciting :wink:

### RPath patching

The problem above has a solution: RPaths! Rpaths are both searched before `LD_LIBRARY_PATH` (they take priority over `LD_LIBRARY_PATH`s) and they can be patched after the library has already been compiled. The RPath patching can be acheived using tools like patchelf, which is the tool we are using here. For more info: <https://www.qt.io/blog/2011/10/28/rpath-and-runpath>

But how does a dependency know the `rpath` of its transitive runtime deps ?

I will answer this with an art work :art: :

<img width="1612" alt="Screenshot 2023-05-02 at 16 27 38" src="https://user-images.githubusercontent.com/8200878/235696979-3784c0a4-a2c8-42b4-a8d3-605a18f55652.png">

<img width="1563" alt="Screenshot 2023-05-02 at 16 28 17" src="https://user-images.githubusercontent.com/8200878/235697542-3f043ecf-8e0d-48b2-8824-08847f2a7489.png">

So basically dependency B needs to be processed ahead of dependency A. It also needs to self-declare all the parent directories of all the ELF files in it. In other words, the dependency graph needs to be processed in a **topological order**.

### Code Workflow - Debian Only

Now in the case of debian packages, the implementation details mentioned above can be translated into the following workflow:

```mermaid
graph TB;
    A[Queue of deb dependencies, deb_q]-->|deb_dep|B{Visited?};
    %% if visited, pop and process next
    B-->|yes|C[Pop deb_q]-->A;
    %% if not in visited, continue
    B-->|no|D[Find transitive dependencies of deb_dep]-->E{Are all transitive dependencies processed? Meaning: did all transitive dependencies declare their rpaths?}-->|yes|F[Modularize and rpath patch deb_dep]-->C;
    %% if not all transitive dep processed already, add them to queue
    E-->|no|G[add unprocessed transitive deps to deb_q]-->A
```

A more detailed view would look like:

```mermaid
graph TB;
    A[Queue of deb dependencies, deb_q]-->|deb_dep|B{Visited?};
    %% if visited, pop and process next
    B-->|yes|C[Pop deb_q]-->A;
    %% if not in visited, check registry
    B-->|no|D{In Registry?};
    %% if in registry, retrieve and mark visited
    D-->|yes|E[Retrieve info from egistry]-->F[Mark as Visited]-->C;
    %% if not in registry, 
    D-->|no|G[apt-get download deb_dep_pinned_name] -->|get transitive deps|H[dpkg-deb -I deb_archive_path]-->|list files|I[dpkg -X deb_archive_path pkg_dir] --> J[get rpath directories]-->K{are all transitive dependency visited?};
    %% if all transitive deps are visited => edge => rpath patch and modularize
    K-->|yes|L[rpath patch ELF files in the package]-->M[Turn package into a module]-->N[Upload as an archive, or add to repo]-->O[reference the module in the registry]-->C;
    %% if all transitive deps are visited => process next
    K-->|no|P[add all non-processed transitive deps to deb_q]-->A;
```
