import { useState, useEffect } from "react";
import {
  PanelSection,
  PanelSectionRow,
  TextField,
  Dropdown,
  Field,
  Toggle,
} from "@decky/ui";
import {
  definePlugin,
  call,
  toaster,
  addEventListener,
  removeEventListener,
} from "@decky/api";
import { FaShip } from "react-icons/fa";

/* ---------------------------------------------------------
   CSS FIX FOR DROPDOWN LABELS
--------------------------------------------------------- */
const _ziplineCSS = document.createElement("style");
_ziplineCSS.innerHTML = `
.DialogButton > span,
.DropdownControlLabel > span,
.DialogMenuButton > span {
  visibility: visible !important;
  opacity: 1 !important;
}
.DialogButton,
.DropdownControlLabel,
.DialogMenuButton {
  color: white !important;
}
.DropdownMenuItem,
.DialogMenuItem {
  color: white !important;
}
`;
document.head.appendChild(_ziplineCSS);
/* --------------------------------------------------------- */

interface PluginSettings {
  uploadURL: string;
  token: string;
  selectedFormat: string;
  useFolder: boolean;
  ziplineFolder: string;
}

interface FolderOption {
  label: string;
  data: string;
}

const formatOptions: FolderOption[] = [
  { label: "DATE", data: "DATE" },
  { label: "UUID", data: "UUID" },
  { label: "RANDOM", data: "RANDOM" },
  { label: "NAME", data: "NAME" },
];

function ZiplineSettingsPage() {
  const [settings, setSettings] = useState<PluginSettings>({
    uploadURL: "",
    token: "",
    selectedFormat: "DATE",
    useFolder: false,
    ziplineFolder: "",
  });

  const [folders, setFolders] = useState<FolderOption[]>([]);

  const loadSettings = async () => {
    const keys = Object.keys(settings) as (keyof PluginSettings)[];
    const out: Partial<PluginSettings> = {};

    for (const key of keys) {
      out[key] = (await call("settings_getSetting", [key, settings[key]])) as any;
    }

    setSettings((prev) => ({ ...prev, ...out }));
  };

  const updateSetting = async (key: keyof PluginSettings, value: any) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    await call("settings_setSetting", [key, value]);
    await call("settings_commit", []);
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const loadFolders = async () => {
    const res = await call("get_folders", []);
    if (Array.isArray(res)) {
      setFolders(
        res.map((f: any) => ({
          label: f.name,
          data: f.id,
        }))
      );
    }
  };

  useEffect(() => {
    if (settings.useFolder && settings.uploadURL && settings.token) {
      loadFolders();
    }
  }, [settings.useFolder, settings.uploadURL, settings.token]);

  useEffect(() => {
    function handleUploadSuccess(localPath: string, url: string) {
      console.log("[Zipline] upload_success:", localPath, url);

      toaster.toast({
        title: "Upload Successful!",
        body: url,
        duration: 3500,
      });
    }

    addEventListener("zipline_upload_success", handleUploadSuccess);

    return () => {
      removeEventListener("zipline_upload_success", handleUploadSuccess);
    };
  }, []);

  return (
    <PanelSection title="Zipline Uploader">

      <PanelSectionRow>
        <TextField
          label="Upload URL"
          value={settings.uploadURL}
          onChange={(e) => updateSetting("uploadURL", e.target.value)}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <TextField
          label="Auth Token"
          value={settings.token}
          onChange={(e) => updateSetting("token", e.target.value)}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <Field label="Format">
          <div style={{ width: "260px" }}>
            <Dropdown
              rgOptions={formatOptions}
              selectedOption={
                formatOptions.find((o) => o.data === settings.selectedFormat) ?? {
                  label: "DATE",
                  data: "DATE",
                }
              }
              onChange={(opt) => updateSetting("selectedFormat", opt.data)}
            />
          </div>
        </Field>
      </PanelSectionRow>

      <PanelSectionRow>
        <Field label="Use Folder">
          <Toggle
            value={settings.useFolder}
            onChange={(v) => updateSetting("useFolder", v)}
          />
        </Field>
      </PanelSectionRow>

      {settings.useFolder && (
        <PanelSectionRow>
          <Field label="Zipline Folder">
            <div style={{ width: "260px" }}>
              <Dropdown
                rgOptions={folders}
                selectedOption={
                  folders.find((f) => f.data === settings.ziplineFolder) ?? {
                    label: "Select Folder",
                    data: "",
                  }
                }
                onChange={(opt) => updateSetting("ziplineFolder", opt.data)}
              />
            </div>
          </Field>
        </PanelSectionRow>
      )}

    </PanelSection>
  );
}

export default definePlugin(() => ({
  name: "Zipline Uploader",
  icon: <FaShip />,
  content: <ZiplineSettingsPage />,
}));
