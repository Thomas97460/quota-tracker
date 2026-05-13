{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.services.quota-tracker;
in {
  options.services.quota-tracker = {
    enable = mkEnableOption "Quota Tracker daemon";

    package = mkOption {
      type = types.package;
      default = pkgs.quota-tracker;
      defaultText = literalExpression "pkgs.quota-tracker";
      description = "The quota-tracker package to use.";
    };
  };

  config = mkIf cfg.enable {
    systemd.user.services.quota-tracker = {
      description = "Quota Tracker Daemon";
      wantedBy = [ "default.target" ];
      after = [ "network.target" ];

      serviceConfig = {
        Type = "simple";
        ExecStart = "${cfg.package}/bin/quota-tracker daemon";
        Restart = "on-failure";
        StandardOutput = "journal";
        StandardError = "journal";
      };
    };
  };
}
