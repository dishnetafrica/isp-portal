/**
 * GenieACS Provision Script
 * Auto-configures TR-069 devices when they first connect
 */

// Get device info
const now = Date.now();
const deviceId = declare("DeviceID.ID", {value: now}).value[0];
const manufacturer = declare("DeviceID.Manufacturer", {value: now}).value[0];
const productClass = declare("DeviceID.ProductClass", {value: now}).value[0];
const serialNumber = declare("DeviceID.SerialNumber", {value: now}).value[0];

log(`Device connected: ${manufacturer} ${productClass} (${serialNumber})`);

// Refresh basic device parameters on every inform
declare("InternetGatewayDevice.DeviceInfo.*", {value: now});
declare("InternetGatewayDevice.ManagementServer.*", {value: now});

// Configure periodic inform interval (every 5 minutes)
declare("InternetGatewayDevice.ManagementServer.PeriodicInformEnable", {value: now}, {value: true});
declare("InternetGatewayDevice.ManagementServer.PeriodicInformInterval", {value: now}, {value: 300});

// Refresh WiFi parameters
declare("InternetGatewayDevice.LANDevice.1.WLANConfiguration.*", {value: now});

// Refresh WAN parameters  
declare("InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANIPConnection.*", {value: now});

// Device-specific configurations
if (manufacturer === "TP-Link" || manufacturer === "TP-LINK") {
    log("Applying TP-Link specific configuration");
    // TP-Link specific parameters
    declare("InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.Enable", {value: now});
    declare("InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID", {value: now});
}

if (manufacturer === "D-Link" || manufacturer === "D-LINK") {
    log("Applying D-Link specific configuration");
    // D-Link specific parameters
    declare("InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.Enable", {value: now});
    declare("InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID", {value: now});
}

// Tag new devices for review
const registered = declare("Tags.registered", {value: now}).value[0];
if (!registered) {
    declare("Tags.new-device", {value: now}, {value: true});
    log(`New device registered: ${serialNumber}`);
}
