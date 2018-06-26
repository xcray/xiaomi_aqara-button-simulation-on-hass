# xiaomi_aqara button simulation on home assistant
add a new service to the xiaomi_aqara component: simulating click/double_click of the wireless button.

capbility to simulate actions of the wireless button is important for me (maybe someone else also need it), so I try to modified the code.

2 files involved:

- homeassistant/components/xiaomi_aqara.py

add the code for new service.

by the way, I'd delete 'light' in line 149 due to the issue https://github.com/home-assistant/home-assistant/issues/15005.

if you think that issue is not a problem to you, just add 'light' back

- homeassistant/components/services.yaml

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
