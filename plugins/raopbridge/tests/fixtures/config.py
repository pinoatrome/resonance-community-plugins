# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License,
# version 2.

full_config = """<?xml version="1.0"?>
<squeeze2raop>
<common>
<streambuf_size>2097152</streambuf_size>
<output_size>1764000</output_size>
<enabled>1</enabled>
<codecs>aac,ogg,ops,ogf,flc,alc,wav,aif,pcm,mp3</codecs>
<sample_rate>96000</sample_rate>
<resolution></resolution>
<resample>1</resample>
<resample_options></resample_options>
<player_volume>-1</player_volume>
<volume_mapping>-30:1, -15:50, 0:100</volume_mapping>
<volume_feedback>1</volume_feedback>
<volume_mode>2</volume_mode>
<mute_on_pause>1</mute_on_pause>
<send_metadata>1</send_metadata>
<send_coverart>1</send_coverart>
<auto_play>0</auto_play>
<idle_timeout>30</idle_timeout>
<remove_timeout>0</remove_timeout>
<alac_encode>0</alac_encode>
<encryption>0</encryption>
<read_ahead>1000</read_ahead>
<server>?</server>
</common>
<interface>?</interface>
<slimproto_log>info</slimproto_log>
<stream_log>warn</stream_log>
<output_log>info</output_log>
<decode_log>warn</decode_log>
<main_log>info</main_log>
<slimmain_log>info</slimmain_log>
<raop_log>info</raop_log>
<util_log>info</util_log>
<log_limit>-1</log_limit>
<migration>3</migration>
<ports>0:0</ports>
<device>
<udn>501E2D00C554@Beosound Shape Sala._raop._tcp.local</udn>
<name>BeoSound-Shape-27779589</name>
<friendly_name>BeoSound-Shape-27779589</friendly_name>
<mac>aa:aa:2d:00:c5:54</mac>
<enabled>1</enabled>
</device>
<device>
<udn>6E6E934B09DB@MacBook Pro._raop._tcp.local</udn>
<name>MacBookProM3</name>
<friendly_name>MacBookProM3</friendly_name>
<mac>aa:aa:88:78:6d:24</mac>
<enabled>1</enabled>
</device>
<device>
<udn>F6B6AAF36CD6@M3 Mac Mini._raop._tcp.local</udn>
<name>mac-mini</name>
<friendly_name>mac-mini</friendly_name>
<mac>aa:aa:77:6d:ae:04</mac>
<enabled>1</enabled>
</device>
<device>
<udn>F4E11E442BB5@BeoPlay A9 Camera._raop._tcp.local</udn>
<name>BeoPlay-A9-30588709</name>
<friendly_name>BeoPlay-A9-30588709</friendly_name>
<mac>aa:aa:1e:44:2b:b5</mac>
<enabled>1</enabled>
</device>
<device>
<udn>501E2D1D1B62@Beoplay M3 Grigio._raop._tcp.local</udn>
<name>Beoplay-M3-28977299</name>
<friendly_name>Beoplay-M3-28977299</friendly_name>
<mac>aa:aa:d8:00:25:39</mac>
<enabled>1</enabled>
</device>
</squeeze2raop>
"""
