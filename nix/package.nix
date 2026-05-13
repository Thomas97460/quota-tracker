{
  lib,
  buildNpmPackage,
  python312Packages,
}:
let
  pyproject = builtins.fromTOML (builtins.readFile ../pyproject.toml);
  pname = pyproject.project.name;
  version = pyproject.project.version;

  frontend = buildNpmPackage {
    pname = "${pname}-frontend";
    inherit version;
    src = ../frontend;
    npmDepsHash = "sha256-CzfezurcDIJJxCDNb/+5+2r+tutqZ1pIEBSNRw1c/Qg=";
    npmBuildScript = "build";

    installPhase = ''
      runHook preInstall
      mkdir -p $out
      cp -r dist $out/dist
      runHook postInstall
    '';
  };
in
python312Packages.buildPythonApplication {
  inherit pname version;
  pyproject = true;
  src = lib.cleanSource ../.;

  build-system = with python312Packages; [
    setuptools
    wheel
  ];

  dependencies = with python312Packages; [
    fastapi
    httpx
    uvicorn
    pydantic
  ];

  nativeCheckInputs = with python312Packages; [
    pytestCheckHook
    pytest-cov
  ];

  preCheck = ''
    export HOME=$TMPDIR
  '';

  postPatch = ''
    rm -rf quota_tracker/frontend_dist
    mkdir -p quota_tracker/frontend_dist
    cp -r ${frontend}/dist/* quota_tracker/frontend_dist/
  '';

  pythonImportsCheck = [ "quota_tracker" ];

  meta = with lib; {
    description = "Track token usage and quotas for Claude, Copilot, Codex, and Gemini";
    homepage = "https://github.com/Thomas97460/quota-tracker";
    license = licenses.mit;
    mainProgram = "quota-tracker";
    platforms = platforms.unix;
    maintainers = with maintainers; [ ];
  };
}
