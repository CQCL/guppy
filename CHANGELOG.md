# Changelog

## [0.15.0](https://github.com/CQCL/guppylang/compare/v0.14.0...v0.15.0) (2025-01-08)


### ⚠ BREAKING CHANGES

* `pytket` circuits no longer supported by `py` expressions (use `@pytket` or `load_pytket` instead)

### Features

* add `panic` builtin function ([#757](https://github.com/CQCL/guppylang/issues/757)) ([4ae3032](https://github.com/CQCL/guppylang/commit/4ae3032088771166de867c5d8f2f19924d9e0cd3))
* add boolean xor support ([#747](https://github.com/CQCL/guppylang/issues/747)) ([7fa4c8d](https://github.com/CQCL/guppylang/commit/7fa4c8d6cf94bf19faa618d4d48d023da1484514)), closes [#750](https://github.com/CQCL/guppylang/issues/750)
* Add string type ([#733](https://github.com/CQCL/guppylang/issues/733)) ([aa9341b](https://github.com/CQCL/guppylang/commit/aa9341b13c9277756296dd98a86989e23c40e3a8))
* Remove circuits from `py` expressions ([#746](https://github.com/CQCL/guppylang/issues/746)) ([ee8926b](https://github.com/CQCL/guppylang/commit/ee8926bb5f3a6b43aea105f702c0e4ff3202b79b))
* support integer exponentiation in guppy source ([#753](https://github.com/CQCL/guppylang/issues/753)) ([70c8fcf](https://github.com/CQCL/guppylang/commit/70c8fcf1cbe009f5938cffc5df2a274cb85eee99))


### Bug Fixes

* Allow string py expressions in result and panic ([#759](https://github.com/CQCL/guppylang/issues/759)) ([53401cc](https://github.com/CQCL/guppylang/commit/53401cc9bcc51844a59258e505ece941687ca32f))
* Fix pytest hanging ([#754](https://github.com/CQCL/guppylang/issues/754)) ([9ad02bb](https://github.com/CQCL/guppylang/commit/9ad02bbb92a5d798398376647a7431669e72d4bc))
* panic on negative exponent in ipow ([#758](https://github.com/CQCL/guppylang/issues/758)) ([821771a](https://github.com/CQCL/guppylang/commit/821771a12a3aff93a5f7661211197818f3905b3b))
* Properly report errors for unsupported subscript assignments ([#738](https://github.com/CQCL/guppylang/issues/738)) ([8afa2a9](https://github.com/CQCL/guppylang/commit/8afa2a93ae224c57932eb6042464f5722668f742)), closes [#736](https://github.com/CQCL/guppylang/issues/736)
* remove newlines in extension description ([#762](https://github.com/CQCL/guppylang/issues/762)) ([2f5eed3](https://github.com/CQCL/guppylang/commit/2f5eed3f9064ae92d397940a337d6453ab9206ce))

## [0.14.0](https://github.com/CQCL/guppylang/compare/v0.13.1...v0.14.0) (2024-12-19)


### ⚠ BREAKING CHANGES

* Lists in `py(...)` expressions are now turned into Guppy arrays instead of lists.
* `dirty_qubit` function removed
* measure_return renamed to `project_z`

### Features

* add `maybe_qubit` stdlib function ([#705](https://github.com/CQCL/guppylang/issues/705)) ([a49f70e](https://github.com/CQCL/guppylang/commit/a49f70e15048efc5a30ef34625086b341b278db6)), closes [#627](https://github.com/CQCL/guppylang/issues/627)
* add measure_array and discard_array quantum function ([#710](https://github.com/CQCL/guppylang/issues/710)) ([3ad49ff](https://github.com/CQCL/guppylang/commit/3ad49ff43ceb8f08001bba3edd9e43d32912747a))
* Add method to load pytket circuit without function stub ([#712](https://github.com/CQCL/guppylang/issues/712)) ([ee1e3de](https://github.com/CQCL/guppylang/commit/ee1e3defb941e9da29f462afc4c16f3e97147828))
* Add Option type to standard library ([#696](https://github.com/CQCL/guppylang/issues/696)) ([45ea6b7](https://github.com/CQCL/guppylang/commit/45ea6b7086f75f017eb4830f55dca9c87d9f599b))
* Allow generic nat args in statically sized ranges ([#706](https://github.com/CQCL/guppylang/issues/706)) ([f441bb8](https://github.com/CQCL/guppylang/commit/f441bb8e56e1006acd1fa37c6f3edada5a8fc537)), closes [#663](https://github.com/CQCL/guppylang/issues/663)
* Array comprehension ([#613](https://github.com/CQCL/guppylang/issues/613)) ([fdc0526](https://github.com/CQCL/guppylang/commit/fdc052656c6b62a95d42e0757ea50bd1d0226571)), closes [#614](https://github.com/CQCL/guppylang/issues/614) [#616](https://github.com/CQCL/guppylang/issues/616) [#612](https://github.com/CQCL/guppylang/issues/612)
* Implicit coercion of numeric types ([#702](https://github.com/CQCL/guppylang/issues/702)) ([df4745b](https://github.com/CQCL/guppylang/commit/df4745bd9343be777ddb78373db5217f63744e61)), closes [#701](https://github.com/CQCL/guppylang/issues/701)
* Load `pytket` circuit as a function definition ([#672](https://github.com/CQCL/guppylang/issues/672)) ([b21b7e1](https://github.com/CQCL/guppylang/commit/b21b7e132a22363b9c2d69485a3f1f4d127b8129))
* Make arrays iterable ([#632](https://github.com/CQCL/guppylang/issues/632)) ([07b9871](https://github.com/CQCL/guppylang/commit/07b987129409bf22d09b80661163f206ffc68f48))
* qsystem std functions with updated primitives ([#679](https://github.com/CQCL/guppylang/issues/679)) ([b0f041f](https://github.com/CQCL/guppylang/commit/b0f041f262c4757b5f519d3a28f0c2b2d038f623))
* remove dirty_qubit ([#698](https://github.com/CQCL/guppylang/issues/698)) ([78e366b](https://github.com/CQCL/guppylang/commit/78e366b1032afefcdedc6f4b78b30999f0e67d2d))
* Turn py expression lists into arrays ([#697](https://github.com/CQCL/guppylang/issues/697)) ([d52a00a](https://github.com/CQCL/guppylang/commit/d52a00ae6f9c33d9fe65ddd46bcf94e39f53172f))
* Unpacking assignment of iterable types with static size ([#688](https://github.com/CQCL/guppylang/issues/688)) ([602e243](https://github.com/CQCL/guppylang/commit/602e2434acb07ca5906d867affe9d4fd1a06d59d))
* update to hugr 0.10 and tket2 0.6 ([#725](https://github.com/CQCL/guppylang/issues/725)) ([63ea7a7](https://github.com/CQCL/guppylang/commit/63ea7a726edc2512e63b89076db5b4c82bec58af))


### Bug Fixes

* Accept non-negative int literals and py expressions as nats ([#708](https://github.com/CQCL/guppylang/issues/708)) ([a93d4fe](https://github.com/CQCL/guppylang/commit/a93d4fe0b07e99bd0537f51a21f9cbf3c0502360)), closes [#704](https://github.com/CQCL/guppylang/issues/704)
* Allow borrowing inside comprehensions ([#723](https://github.com/CQCL/guppylang/issues/723)) ([02b6ab0](https://github.com/CQCL/guppylang/commit/02b6ab00f96a7801199d0ec2d3c017d7d81cdf59)), closes [#719](https://github.com/CQCL/guppylang/issues/719)
* Detect unsupported default arguments ([#659](https://github.com/CQCL/guppylang/issues/659)) ([94ac7e3](https://github.com/CQCL/guppylang/commit/94ac7e38c773e4aac8b809ae27cf7e18342a87cb)), closes [#658](https://github.com/CQCL/guppylang/issues/658)
* docs build command ([#729](https://github.com/CQCL/guppylang/issues/729)) ([471b74c](https://github.com/CQCL/guppylang/commit/471b74c2bf5ca6144d6a5dec71b8a0e4aec57a95))
* Ensure `int`s can be treated as booleans ([#709](https://github.com/CQCL/guppylang/issues/709)) ([6ef6d60](https://github.com/CQCL/guppylang/commit/6ef6d608dc8c92c7045575fe579637ca482f3516)), closes [#681](https://github.com/CQCL/guppylang/issues/681)
* Fix array execution bugs ([#731](https://github.com/CQCL/guppylang/issues/731)) ([0f6ceaa](https://github.com/CQCL/guppylang/commit/0f6ceaa58648f105e601298081170eaec5a0e026))
* Fix implicit modules in IPython shells ([#662](https://github.com/CQCL/guppylang/issues/662)) ([4ecb5f2](https://github.com/CQCL/guppylang/commit/4ecb5f2fb2dd5b4b9baa5546869c46d42c709017)), closes [#661](https://github.com/CQCL/guppylang/issues/661)
* Properly report error for unsupported constants ([#724](https://github.com/CQCL/guppylang/issues/724)) ([d0c2da4](https://github.com/CQCL/guppylang/commit/d0c2da40cdf1fe4e770123d4174bf710dd44e1a6)), closes [#721](https://github.com/CQCL/guppylang/issues/721)
* Properly report errors for unsupported expressions ([#692](https://github.com/CQCL/guppylang/issues/692)) ([7f24264](https://github.com/CQCL/guppylang/commit/7f24264a56b0b620847a189eeec565f80adbdc3a)), closes [#691](https://github.com/CQCL/guppylang/issues/691)
* remove use of deprecated Ellipsis ([#699](https://github.com/CQCL/guppylang/issues/699)) ([b819a84](https://github.com/CQCL/guppylang/commit/b819a844286cfb17ede045a7cb4f52325a36c63f))


### Documentation

* Fix docs build ([#700](https://github.com/CQCL/guppylang/issues/700)) ([684f485](https://github.com/CQCL/guppylang/commit/684f485f98ea4cc4f61040af00fbde0b0c908e45)), closes [#680](https://github.com/CQCL/guppylang/issues/680)
* fix README.md and quickstart.md ([#654](https://github.com/CQCL/guppylang/issues/654)) ([abb0221](https://github.com/CQCL/guppylang/commit/abb0221a46c3dcb069c6e0f08242319d7bb16bad))

## [0.13.1](https://github.com/CQCL/guppylang/compare/v0.13.0...v0.13.1) (2024-11-15)


### Features

* Generic function definitions ([#618](https://github.com/CQCL/guppylang/issues/618)) ([7519b90](https://github.com/CQCL/guppylang/commit/7519b9096a02cf75672313bd0bc90c613e5230ee)), closes [#522](https://github.com/CQCL/guppylang/issues/522)
* mem_swap function for swapping two inout values ([#653](https://github.com/CQCL/guppylang/issues/653)) ([89e10a5](https://github.com/CQCL/guppylang/commit/89e10a5e5c4344badcd0a0a16983c8a3a560ad09))


### Bug Fixes

* Fix generic array functions ([#630](https://github.com/CQCL/guppylang/issues/630)) ([f4e5655](https://github.com/CQCL/guppylang/commit/f4e5655e0a85d773ec21fc4a9f7a6c23263dae0a))

## [0.13.0](https://github.com/CQCL/guppylang/compare/v0.12.2...v0.13.0) (2024-11-12)


### ⚠ BREAKING CHANGES

* `prelude` module renamed to `std`

### Features

* add `qubit` discard/measure methods ([#580](https://github.com/CQCL/guppylang/issues/580)) ([242fa44](https://github.com/CQCL/guppylang/commit/242fa44f45e676e81efd5df48de9fc80fe0ea516))
* Add `SizedIter` wrapper type ([#611](https://github.com/CQCL/guppylang/issues/611)) ([2e9da6b](https://github.com/CQCL/guppylang/commit/2e9da6be24de499f059c3cdb7553604cb9373ca0))
* conventional results post processing ([#593](https://github.com/CQCL/guppylang/issues/593)) ([db96224](https://github.com/CQCL/guppylang/commit/db962243670fea4987ef842c67a59f560f08f72a))
* Improve compiler diagnostics ([#547](https://github.com/CQCL/guppylang/issues/547)) ([90d465d](https://github.com/CQCL/guppylang/commit/90d465d87bdde777302381367598812e37c501e7)), closes [#551](https://github.com/CQCL/guppylang/issues/551) [#553](https://github.com/CQCL/guppylang/issues/553) [#586](https://github.com/CQCL/guppylang/issues/586) [#588](https://github.com/CQCL/guppylang/issues/588) [#587](https://github.com/CQCL/guppylang/issues/587) [#590](https://github.com/CQCL/guppylang/issues/590) [#600](https://github.com/CQCL/guppylang/issues/600) [#601](https://github.com/CQCL/guppylang/issues/601) [#606](https://github.com/CQCL/guppylang/issues/606)
* restrict result tag sizes to 256 bytes ([#596](https://github.com/CQCL/guppylang/issues/596)) ([4e8e00f](https://github.com/CQCL/guppylang/commit/4e8e00ffe733b1b65055f2355d6a538334449e6d)), closes [#595](https://github.com/CQCL/guppylang/issues/595)


### Bug Fixes

* Mock guppy decorator during sphinx builds ([#622](https://github.com/CQCL/guppylang/issues/622)) ([1cccc04](https://github.com/CQCL/guppylang/commit/1cccc04c54c3c3f38e1e2c1ce828935091e07cad))


### Documentation

* Add DEVELOPMENT.md ([#584](https://github.com/CQCL/guppylang/issues/584)) ([1d29d39](https://github.com/CQCL/guppylang/commit/1d29d393206484324835764e89dff7a39c83b3f9))
* Fix docs build ([#639](https://github.com/CQCL/guppylang/issues/639)) ([bd6011c](https://github.com/CQCL/guppylang/commit/bd6011cd0e7817fbac24a1b28a8d33ea93c92bef))


### Miscellaneous Chores

* Manually set last release commit ([#643](https://github.com/CQCL/guppylang/issues/643)) ([b2d569b](https://github.com/CQCL/guppylang/commit/b2d569b19ac0001841bdd2c326447dbeee40d20c))


### Code Refactoring

* rename prelude to std ([#642](https://github.com/CQCL/guppylang/issues/642)) ([1a68e8e](https://github.com/CQCL/guppylang/commit/1a68e8e7919487f1465cc587b9855cb43169f63d))

## [0.12.2](https://github.com/CQCL/guppylang/compare/v0.12.1...v0.12.2) (2024-10-21)


### Features

* Allow py expressions in type arguments ([#515](https://github.com/CQCL/guppylang/issues/515)) ([b4fae3f](https://github.com/CQCL/guppylang/commit/b4fae3f7a29b384f8bbe0069dc6131ec115e17ee))
* remove python python 3 upper bound (support python 3.13) ([#578](https://github.com/CQCL/guppylang/issues/578)) ([73bb94a](https://github.com/CQCL/guppylang/commit/73bb94a76731afff7edfce681b556122fef486c7)), closes [#558](https://github.com/CQCL/guppylang/issues/558)


### Bug Fixes

* Enable len for linear arrays ([#576](https://github.com/CQCL/guppylang/issues/576)) ([117b68e](https://github.com/CQCL/guppylang/commit/117b68e6b74221ec85822f721c23c8245e2294fe)), closes [#570](https://github.com/CQCL/guppylang/issues/570)
* Fix array lowering bugs ([#575](https://github.com/CQCL/guppylang/issues/575)) ([83b9f31](https://github.com/CQCL/guppylang/commit/83b9f312e3465d83318feaf0f5a8af6a5ed9fa45))
* Fix printing of generic function parameters ([#516](https://github.com/CQCL/guppylang/issues/516)) ([5c18ef6](https://github.com/CQCL/guppylang/commit/5c18ef63237ad76a4b0f74d8b3c4d77a438052ef)), closes [#482](https://github.com/CQCL/guppylang/issues/482)


## [0.12.1](https://github.com/CQCL/guppylang/compare/v0.12.0...v0.12.1) (2024-09-23)


### Features

* Add Definition.compile producing Hugr Package ([#504](https://github.com/CQCL/guppylang/issues/504)) ([d8c8bec](https://github.com/CQCL/guppylang/commit/d8c8bec33075e015dc12d8142891f566c3249c92))
* Add missing tket2 quantum gates, generalise RotationCompile ([#510](https://github.com/CQCL/guppylang/issues/510)) ([18d4b4c](https://github.com/CQCL/guppylang/commit/18d4b4c8b324b0f202e262768617d450745004dc))


### Miscellaneous Chores

* release 0.12.1 ([#512](https://github.com/CQCL/guppylang/issues/512)) ([b309a94](https://github.com/CQCL/guppylang/commit/b309a944af3d45a6afbdf6fd253b3b764e36c029))

## [0.12.0](https://github.com/CQCL/guppylang/compare/v0.11.0...v0.12.0) (2024-09-18)


### ⚠ BREAKING CHANGES

* Pytket circuits loaded via a `py` expression no longer take ownership of the passed qubits.
* Lists and function tensors are no longer available by default. `guppylang.enable_experimental_features()` must be called before compilation to enable them.
* The `GuppyModule` argument is now optional for all decorators and no longer the first positional argument. Removed the explicit module objects `builtins`, `quantum`, and `angle`.
* `quantum_functional` is now its own Guppy module and no longer implicitly comes with `quantum`.
* Linear function arguments are now borrowed by default; removed the now redundant `@inout` annotation

### Features

* Add functions to quantum module and make quantum_functional independent ([#494](https://github.com/CQCL/guppylang/issues/494)) ([0b0b1af](https://github.com/CQCL/guppylang/commit/0b0b1afbf5bf481d8fdcbe5050dcf9d5fb85d263))
* Hide lists and function tensors behind experimental flag ([#501](https://github.com/CQCL/guppylang/issues/501)) ([c867f48](https://github.com/CQCL/guppylang/commit/c867f48d6dc555454db69943f0b420cb53676d3d))
* Make linear types [@inout](https://github.com/inout) by default; add [@owned](https://github.com/owned) annotation ([#486](https://github.com/CQCL/guppylang/issues/486)) ([e900c96](https://github.com/CQCL/guppylang/commit/e900c96eb3755ad5d4304eb721e791b8185c8f09))
* Only lower definitions to Hugr if they are used ([#496](https://github.com/CQCL/guppylang/issues/496)) ([cc2c8a4](https://github.com/CQCL/guppylang/commit/cc2c8a4f09f43f8913c49ff0dfe0da601a85b7c6))
* Support implicit modules for all decorators and turn builtins into implicit module ([#476](https://github.com/CQCL/guppylang/issues/476)) ([cc8a424](https://github.com/CQCL/guppylang/commit/cc8a424ad9a8b8c3c5a3b5cc700ccdb7a5ff8fa9))
* Use inout for pytket circuits ([#500](https://github.com/CQCL/guppylang/issues/500)) ([a980ec2](https://github.com/CQCL/guppylang/commit/a980ec2c89e2ebecb16b0ea12750ecf6781f3ee3))


### Bug Fixes

* `angle` is now a struct and emitted as a rotation  ([#485](https://github.com/CQCL/guppylang/issues/485)) ([992b138](https://github.com/CQCL/guppylang/commit/992b138a312dace5a6f846e99013a0a0bcfe74e6))
* Evade false positives for inout variable usage ([#493](https://github.com/CQCL/guppylang/issues/493)) ([6fdb5d6](https://github.com/CQCL/guppylang/commit/6fdb5d6ff1fb4c2e4db89f885480fbe818fd32a0))
* Fix redefinition of structs ([#499](https://github.com/CQCL/guppylang/issues/499)) ([0b156e9](https://github.com/CQCL/guppylang/commit/0b156e9f9894b45fc2ca6c566e496d9242634434))
* Initialise _checked in GuppyModule ([#491](https://github.com/CQCL/guppylang/issues/491)) ([3dd5dd3](https://github.com/CQCL/guppylang/commit/3dd5dd3797f1da8b1bd0acdee692d1d5e8a19d98)), closes [#489](https://github.com/CQCL/guppylang/issues/489)
* use correct array ops ([#503](https://github.com/CQCL/guppylang/issues/503)) ([720d8b8](https://github.com/CQCL/guppylang/commit/720d8b814bbd3f76e788cedc4db4cef96ff24160))

## [0.11.0](https://github.com/CQCL/guppylang/compare/v0.10.0...v0.11.0) (2024-09-11)


### ⚠ BREAKING CHANGES

* `guppy.take_module` renamed to `guppy.get_module` and no longer removes the module from the state.
* Quantum operations `rx`, `rz`, `phased_x`, and `zz_max` use the `angle` type instead of floats.

### Features

* Add implicit importing of modules ([#461](https://github.com/CQCL/guppylang/issues/461)) ([1b73032](https://github.com/CQCL/guppylang/commit/1b730320d6f6b7d6a1062f5322ccec0cd888380f))
* Use angle type in quantum operations ([#467](https://github.com/CQCL/guppylang/issues/467)) ([ce0f746](https://github.com/CQCL/guppylang/commit/ce0f746dfe6702c68a850380ef8965e58f666354))


### Bug Fixes

* hseries ops use floats instead of angles ([#483](https://github.com/CQCL/guppylang/issues/483)) ([7ed3853](https://github.com/CQCL/guppylang/commit/7ed38531bed8dba65859c2185858bee5bb22a000)), closes [#477](https://github.com/CQCL/guppylang/issues/477)
* Keep track of definitions that are implicitly imported ([#481](https://github.com/CQCL/guppylang/issues/481)) ([a89f225](https://github.com/CQCL/guppylang/commit/a89f2251eb753803c2e67aee4bd21ae40f83a5ba)), closes [#480](https://github.com/CQCL/guppylang/issues/480)

## [0.10.0](https://github.com/CQCL/guppylang/compare/v0.9.0...v0.10.0) (2024-09-11)


### ⚠ BREAKING CHANGES

* Bumped the `hugr` dependency to `0.8.0`
* `GuppyModule.load` no longer loads the content of modules but instead just brings the name of the module into scope. Use `GuppyModule.load_all` to get the old behaviour.
* Removed `guppylang.hugr_builder.hugr.Hugr`, compiling a module returns a `hugr.Package` instead.

### Features

* Add `__version__` field to guppylang ([#473](https://github.com/CQCL/guppylang/issues/473)) ([b996c62](https://github.com/CQCL/guppylang/commit/b996c62a5f1f5d643fb9a2be893911f6021dd0e9))
* Add angle type ([#449](https://github.com/CQCL/guppylang/issues/449)) ([12e41e0](https://github.com/CQCL/guppylang/commit/12e41e02354a504b8a527a48b6df8f2ed51891df))
* Add array literals ([#446](https://github.com/CQCL/guppylang/issues/446)) ([a255c02](https://github.com/CQCL/guppylang/commit/a255c02f7e1c525b7534f5b08a5c3d6f1fb79392))
* Add equality test for booleans ([#394](https://github.com/CQCL/guppylang/issues/394)) ([dd702ce](https://github.com/CQCL/guppylang/commit/dd702ce5e5e5f363b3a31e0075690703f2fe6d29)), closes [#363](https://github.com/CQCL/guppylang/issues/363)
* Add pi constant ([#451](https://github.com/CQCL/guppylang/issues/451)) ([9d35a78](https://github.com/CQCL/guppylang/commit/9d35a78b784ba0c00bcdf3d2a1256606fb797644))
* Add qualified imports and make them the default ([#443](https://github.com/CQCL/guppylang/issues/443)) ([553ec51](https://github.com/CQCL/guppylang/commit/553ec51d071ed6f195322685590335fa1712c4a7))
* Allow calling of methods ([#440](https://github.com/CQCL/guppylang/issues/440)) ([5a59da3](https://github.com/CQCL/guppylang/commit/5a59da359ee7a098ce069db5cdebd5eb98ec9781))
* Allow imports of function definitions and aliased imports ([#432](https://github.com/CQCL/guppylang/issues/432)) ([e23b666](https://github.com/CQCL/guppylang/commit/e23b6668ef0716f7dabb91be73a217c11ca32ecc))
* Array indexing ([#415](https://github.com/CQCL/guppylang/issues/415)) ([2199b48](https://github.com/CQCL/guppylang/commit/2199b48d777c28cf5584f537d78360d15d4c924b)), closes [#421](https://github.com/CQCL/guppylang/issues/421) [#422](https://github.com/CQCL/guppylang/issues/422) [#447](https://github.com/CQCL/guppylang/issues/447)
* Inout arguments ([#311](https://github.com/CQCL/guppylang/issues/311)) ([060649b](https://github.com/CQCL/guppylang/commit/060649b8e1249489dd5851e0a8578ab715e093ce)), closes [#315](https://github.com/CQCL/guppylang/issues/315) [#316](https://github.com/CQCL/guppylang/issues/316) [#349](https://github.com/CQCL/guppylang/issues/349) [#344](https://github.com/CQCL/guppylang/issues/344) [#321](https://github.com/CQCL/guppylang/issues/321) [#331](https://github.com/CQCL/guppylang/issues/331) [#350](https://github.com/CQCL/guppylang/issues/350) [#340](https://github.com/CQCL/guppylang/issues/340) [#351](https://github.com/CQCL/guppylang/issues/351)
* range() with single-argument ([#452](https://github.com/CQCL/guppylang/issues/452)) ([d05f369](https://github.com/CQCL/guppylang/commit/d05f369041edbb10772117161d3a74414769361d))
* Skip checking of redefined functions ([#457](https://github.com/CQCL/guppylang/issues/457)) ([7f9ad32](https://github.com/CQCL/guppylang/commit/7f9ad32906e909c552025063c062d8b79d43325a))
* Support `nat`/`int` ↔ `bool` cast operations ([#459](https://github.com/CQCL/guppylang/issues/459)) ([3b778c3](https://github.com/CQCL/guppylang/commit/3b778c3649b8c54b29faa907e3fd95e9ae87e5bd))
* Use `hugr-cli` for validation ([#455](https://github.com/CQCL/guppylang/issues/455)) ([1d0667b](https://github.com/CQCL/guppylang/commit/1d0667bc06998a6682352b46758f5465ef4ae22c))
* Use cell name instead of file for notebook errors ([#382](https://github.com/CQCL/guppylang/issues/382)) ([d542601](https://github.com/CQCL/guppylang/commit/d5426017320efba8ed8cf2024c37a0b64b0cdce9))
* Use the hugr builder ([536abf9](https://github.com/CQCL/guppylang/commit/536abf9ff82899332c960695da9e620bbdbf3d8b))


### Bug Fixes

* Fix and update demo notebook ([#376](https://github.com/CQCL/guppylang/issues/376)) ([23b2a15](https://github.com/CQCL/guppylang/commit/23b2a1559271ce36a348384616603bef67c73992))
* Fix linearity checking bug ([#441](https://github.com/CQCL/guppylang/issues/441)) ([0b8ea21](https://github.com/CQCL/guppylang/commit/0b8ea21763fd3611a2b5ec2a978b14954d5a9582))
* Fix struct definitions in notebooks ([#374](https://github.com/CQCL/guppylang/issues/374)) ([b009465](https://github.com/CQCL/guppylang/commit/b009465d8221bb22576bfb079d05b01e1872d500))


### Documentation

* Update readme, `cargo build` instead of  `--extra validation` ([#471](https://github.com/CQCL/guppylang/issues/471)) ([c2a4c86](https://github.com/CQCL/guppylang/commit/c2a4c86a81378447ecaa64ba5090da22971d7303))


### Miscellaneous Chores

* Update hugr to `0.8.0` ([#454](https://github.com/CQCL/guppylang/issues/454)) ([b02e0d0](https://github.com/CQCL/guppylang/commit/b02e0d017e60469051ddfc84c8cd28003a40286d))

## [0.9.0](https://github.com/CQCL/guppylang/compare/v0.8.1...v0.9.0) (2024-08-12)


### ⚠ BREAKING CHANGES

* 

### Bug Fixes

* Use latest results extension spec ([#370](https://github.com/CQCL/guppylang/issues/370)) ([d9cc8d2](https://github.com/CQCL/guppylang/commit/d9cc8d29cce4178c44d00e444d29f7c30fafb7a3))

## [0.8.1](https://github.com/CQCL/guppylang/compare/v0.8.0...v0.8.1) (2024-08-08)


### Bug Fixes

* Fix invalid result operation name ([#367](https://github.com/CQCL/guppylang/issues/367)) ([568624d](https://github.com/CQCL/guppylang/commit/568624d1ccd70dc78c16f4ca2170dc167791ea64))
* Linearity checking bug ([#355](https://github.com/CQCL/guppylang/issues/355)) ([e14660f](https://github.com/CQCL/guppylang/commit/e14660f2b31d104c7fb0b5cb8806c3656098afbb))

## [0.8.0](https://github.com/CQCL/guppylang/compare/v0.7.0...v0.8.0) (2024-07-30)


### Features

* Parse docstrings for functions ([#334](https://github.com/CQCL/guppylang/issues/334)) ([a7cc97a](https://github.com/CQCL/guppylang/commit/a7cc97a6c1af674972c3a37e28ef7e33ddf6fa3d))


### Bug Fixes

* Use places in BB signatures for Hugr generation ([#342](https://github.com/CQCL/guppylang/issues/342)) ([48b0e35](https://github.com/CQCL/guppylang/commit/48b0e352d835298b66ea90ff12528391c1c0e2a3))

## [0.7.0](https://github.com/CQCL/guppylang/compare/v0.6.2...v0.7.0) (2024-07-25)


### ⚠ BREAKING CHANGES

* `qubit`s are now reset on allocation

### Features

* `qubit`s are now reset on allocation, and `dirty_qubit` added ([#325](https://github.com/CQCL/guppylang/issues/325)) ([4a9e205](https://github.com/CQCL/guppylang/commit/4a9e20529a4d0859f010fad62ba06f62ca1c98ce))
* Allow access to struct fields and mutation of linear ones ([#295](https://github.com/CQCL/guppylang/issues/295)) ([6698b75](https://github.com/CQCL/guppylang/commit/6698b75b01421cd1fa545219786266fb0c1da05b)), closes [#293](https://github.com/CQCL/guppylang/issues/293)
* Allow redefinition of names in guppy modules ([#326](https://github.com/CQCL/guppylang/issues/326)) ([314409c](https://github.com/CQCL/guppylang/commit/314409cd63b544d0fdbf16db66201b08dead81fe)), closes [#307](https://github.com/CQCL/guppylang/issues/307)


### Bug Fixes

* Use correct hook for error printing inside jupyter notebooks ([#324](https://github.com/CQCL/guppylang/issues/324)) ([bfdb003](https://github.com/CQCL/guppylang/commit/bfdb003d454d3d8fb6385c2c758dab56ab622496)), closes [#323](https://github.com/CQCL/guppylang/issues/323)

## [0.6.2](https://github.com/CQCL/guppylang/compare/v0.6.1...v0.6.2) (2024-07-10)


### Features

* update to hugr-python 0.4  ([af770c3](https://github.com/CQCL/guppylang/commit/af770c31536a59c32fd8229579455a309e90058e))

## [0.6.1](https://github.com/CQCL/guppylang/compare/v0.6.0...v0.6.1) (2024-07-09)


### Features

* update to `hugr-py 0.3` ([3da3936](https://github.com/CQCL/guppylang/commit/3da393674de7d03dd0d5d5b8239dd8968d16c4c4))

## [0.6.0](https://github.com/CQCL/guppylang/compare/v0.5.2...v0.6.0) (2024-07-02)


### Features

* Add array type ([#258](https://github.com/CQCL/guppylang/issues/258)) ([041c621](https://github.com/CQCL/guppylang/commit/041c621a0481f14ee517b0356e0ebb9cae6ddc2e))
* Add nat type ([#254](https://github.com/CQCL/guppylang/issues/254)) ([a461a9d](https://github.com/CQCL/guppylang/commit/a461a9d5556d7ed68da5a722100c8b3fb449b25e))
* Add result function ([#271](https://github.com/CQCL/guppylang/issues/271)) ([792fb87](https://github.com/CQCL/guppylang/commit/792fb871cac5b19905e87dd485e11d7488f2fb87)), closes [#270](https://github.com/CQCL/guppylang/issues/270)
* Allow constant nats as type args ([#255](https://github.com/CQCL/guppylang/issues/255)) ([d706735](https://github.com/CQCL/guppylang/commit/d7067356c71cbcc5352e69ea4eed6bdc1d0c1ec8))
* Generate constructor methods for structs ([#262](https://github.com/CQCL/guppylang/issues/262)) ([f68d0af](https://github.com/CQCL/guppylang/commit/f68d0afe74c75e40b49babe26091a24d822218f7)), closes [#261](https://github.com/CQCL/guppylang/issues/261)
* Return already-compiled hugrs from `GuppyModule.compile` ([#247](https://github.com/CQCL/guppylang/issues/247)) ([9d01eae](https://github.com/CQCL/guppylang/commit/9d01eae8e4db21a95ad3e97d4e78fea7b4b32c08))
* Turn int and float into core types ([#225](https://github.com/CQCL/guppylang/issues/225)) ([99217dc](https://github.com/CQCL/guppylang/commit/99217dcddb16fa7c713b7e5c5d356715a0fc9496))


### Bug Fixes

* Add missing test file ([#266](https://github.com/CQCL/guppylang/issues/266)) ([75231fe](https://github.com/CQCL/guppylang/commit/75231fe509c52945d44eadb2aa238d1eecf01b0c))
* Loading custom polymorphic function defs as values ([#260](https://github.com/CQCL/guppylang/issues/260)) ([d15b2f5](https://github.com/CQCL/guppylang/commit/d15b2f5a2c012924436ecd3ab482099654a1752e)), closes [#259](https://github.com/CQCL/guppylang/issues/259)

## [0.5.2](https://github.com/CQCL/guppylang/compare/v0.5.1...v0.5.2) (2024-06-13)


### Bug Fixes

* Don't reorder inputs of entry BB ([#243](https://github.com/CQCL/guppylang/issues/243)) ([ad56b99](https://github.com/CQCL/guppylang/commit/ad56b991c03e1bc52690e41450521e7fe9100268))

## [0.5.1](https://github.com/CQCL/guppylang/compare/v0.5.0...v0.5.1) (2024-06-12)


### Bug Fixes

* Serialisation of bool values ([#239](https://github.com/CQCL/guppylang/issues/239)) ([16a77db](https://github.com/CQCL/guppylang/commit/16a77dbd4c5905eff6c4ddabe66b5ef1b8a7e15b))

## [0.5.0](https://github.com/CQCL/guppylang/compare/v0.4.0...v0.5.0) (2024-06-10)


### Features

* Add extern symbols ([#236](https://github.com/CQCL/guppylang/issues/236)) ([977ccd8](https://github.com/CQCL/guppylang/commit/977ccd831a3df1bdf49582309bce065a865d3e31))

## [0.4.0](https://github.com/CQCL/guppylang/compare/v0.3.0...v0.4.0) (2024-05-30)


### Features

* Export py function ([6dca95d](https://github.com/CQCL/guppylang/commit/6dca95deda3cc5bd103df104e33991c9adce2be2))

## [0.3.0](https://github.com/CQCL/guppylang/compare/v0.2.0...v0.3.0) (2024-05-22)


### Features

* Add a unified definition system ([#179](https://github.com/CQCL/guppylang/issues/179)) ([ae71932](https://github.com/CQCL/guppylang/commit/ae71932a608ed5034c060972eb70265ae2dec88c))
* Add struct types ([#207](https://github.com/CQCL/guppylang/issues/207)) ([f7adb85](https://github.com/CQCL/guppylang/commit/f7adb85bfbc7498047471cdf6b232c6b5056e19e))
* Allow calling a tensor of functions ([#196](https://github.com/CQCL/guppylang/issues/196)) ([af4fb07](https://github.com/CQCL/guppylang/commit/af4fb07e4613c8ab5948a681ba336f1f49a49495))
* Upgrade Hugr and start using the shared Pydantic model ([#201](https://github.com/CQCL/guppylang/issues/201)) ([bd7e67a](https://github.com/CQCL/guppylang/commit/bd7e67a59df3c6a8eede15c8a62f4f555d539c9a))


### Bug Fixes

* Consider type when deciding whether to pack up returns ([#212](https://github.com/CQCL/guppylang/issues/212)) ([4f24a07](https://github.com/CQCL/guppylang/commit/4f24a071d3c0b475920141fc5847474f0621b703))
* Mypy tket2 error ([#220](https://github.com/CQCL/guppylang/issues/220)) ([7ad3908](https://github.com/CQCL/guppylang/commit/7ad3908e2bb2672028df3eaa2cd78883020e144f))
* Only use path when determining equality of implicit modules ([#216](https://github.com/CQCL/guppylang/issues/216)) ([6f47d4b](https://github.com/CQCL/guppylang/commit/6f47d4bce55115c6b82d86007f75f40d46796b24))
* Serialisation of float values ([#219](https://github.com/CQCL/guppylang/issues/219)) ([937260a](https://github.com/CQCL/guppylang/commit/937260af694fbbd5bd217f23d20f13ee4759757c)), closes [#218](https://github.com/CQCL/guppylang/issues/218)


### Documentation

* Add compiler API docs ([#194](https://github.com/CQCL/guppylang/issues/194)) ([c3dd9bd](https://github.com/CQCL/guppylang/commit/c3dd9bdf19cbfeb23b792376f2fedf8f4f4dbeaf))
* Add pypi and python version badges to the README ([#192](https://github.com/CQCL/guppylang/issues/192)) ([7fecc45](https://github.com/CQCL/guppylang/commit/7fecc45f3fce8489872dbe65c6012f7cd0b8dc61))

## 0.2.0 (2024-04-11)


### ⚠ BREAKING CHANGES

* Make `qubit` type lower case ([#165](https://github.com/CQCL/guppylang/issues/165))

### Features

* Local implicit modules for `@guppy` ([#105](https://github.com/CQCL/guppylang/issues/105)) ([f52a5de](https://github.com/CQCL/guppylang/commit/f52a5de95972d028167f5800d16573c178c9e2be))
* New type representation with parameters ([#174](https://github.com/CQCL/guppylang/issues/174)) ([73e29f2](https://github.com/CQCL/guppylang/commit/73e29f25ec90b8dfcc6517b961d6d1d13f694cb6))


### Bug Fixes

* Make ZZMax a dyadic operation ([#168](https://github.com/CQCL/guppylang/issues/168)) ([152485f](https://github.com/CQCL/guppylang/commit/152485f08ef61c3450da1e8b03eee883558a6871)), closes [#154](https://github.com/CQCL/guppylang/issues/154)
* Stop exiting interpreter on error ([#140](https://github.com/CQCL/guppylang/issues/140)) ([728e449](https://github.com/CQCL/guppylang/commit/728e44921f20b227ed92f89daae513798701ef62))
* Use correct TK2 gate names ([#190](https://github.com/CQCL/guppylang/issues/190)) ([df92642](https://github.com/CQCL/guppylang/commit/df92642c35b977c0d318747ac1d4011061d6e171))


### Documentation

* add reference to runner to readme ([#129](https://github.com/CQCL/guppylang/issues/129)) ([45c2bf0](https://github.com/CQCL/guppylang/commit/45c2bf010a719785527e1c5cc2ac650975e84d4d))
* Add short description and simplify readme for pypi ([#136](https://github.com/CQCL/guppylang/issues/136)) ([667bba3](https://github.com/CQCL/guppylang/commit/667bba380e7bd38d2e1c66e8e6b67dfbba4efa05))


### Code Refactoring

* Make `qubit` type lower case ([#165](https://github.com/CQCL/guppylang/issues/165)) ([0a42097](https://github.com/CQCL/guppylang/commit/0a42097f617a231a7c6a3096b5d12bda6b19e0aa))


### Continuous Integration

* Use `release-please bootstrap`'s default config ([#187](https://github.com/CQCL/guppylang/issues/187)) ([72e666a](https://github.com/CQCL/guppylang/commit/72e666af5a52c44a4094080a665342422a242d2b))

## [0.1.0](https://github.com/CQCL/guppy/releases/tag/v0.1.0)

First release of Guppy! 🐟

This is an alpha release that implements basic language features and compilation to hugr v0.1.
