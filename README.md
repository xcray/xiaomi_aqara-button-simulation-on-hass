# xiaomi_aqara button simulation on home assistant
add a new service to the xiaomi_aqara component: simulating click/double_click of the wireless button.

capbility to simulate actions of the wireless button is important for me (maybe someone else also need it), so I try to modified the code.

btw, the light on the gateway shouldn't be controled via LAN API, or it will be out of order in native app. so I disabled it.

another issue is about the illumination sensor, I don't know why to modify the value with -300, so I'd modified it.

3 files involved: \__init__.py, sensor.py and services.yaml

put them under the directory of homeassistant/components/xiaomi_aqara/

by the way, I'd delete 'light' in line 149 due to the issue https://github.com/home-assistant/home-assistant/issues/15005.

if you think that issue is not a problem to you, just add 'light' back

- services.yaml

add description of the new service

# usage
provide gw_mac, device_id and status into the json body, for example:
```
{
	"gw_mac": "1122aabb3344",
	"device_id": "158d0000000000",
	"status": "click"
}
```
# Attention
Only tested with lumi.gateway.v3.
If using with a diffrent model of gateway, the code maybe need modification due to the diffrences in the protocol version.

newest code works with version 0.97 of home-assistant
