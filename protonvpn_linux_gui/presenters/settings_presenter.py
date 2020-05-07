import re
import os
import time
import shutil
import subprocess
import collections

# Remote imports
from protonvpn_cli.constants import CONFIG_DIR, PASSFILE, SPLIT_TUNNEL_FILE, USER #noqa
from protonvpn_cli.utils import get_config_value, is_valid_ip, set_config_value, change_file_owner #noqa
from protonvpn_cli.connection import disconnect as pvpn_disconnect
from protonvpn_cli.country_codes import country_codes

# PyGObject import
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GObject as gobject

# Local imports
from protonvpn_linux_gui.gui_logger import gui_logger
from protonvpn_linux_gui.constants import (
    TRAY_CFG_DICT, 
    TEMPLATE,
    PATH_AUTOCONNECT_SERVICE,
    SERVICE_NAME
)
from protonvpn_linux_gui.utils import (
    populate_server_list,
    set_gui_config,
    get_gui_config,
    populate_autoconnect_list,
    find_cli,
)

class SettingsPresenter:
    def __init__(self,  settings_service, queue):
        self.settings_service = settings_service
        self.queue = queue

    def update_user_pass(self, **kwargs):
        """Function that updates username and password.
        """
        dialog_window = kwargs.get("dialog_window")

        username = kwargs.get("username")
        password = kwargs.get("password")

        gui_logger.debug(">>> Running \"set_username_password\".")

        msg = "Unable to update username and password!"
        if self.settings_service.set_user_pass(username, password):
            msg = "Username and password <b>updated</b>!"

        dialog_window.update_dialog(label=msg)

        gui_logger.debug(">>> Ended tasks in \"set_username_password\" thread.")

    def update_dns(self, dns_value):
        """Function that updates DNS settings.
        """
        
        self.settings_service.set_dns(dns_value)

        gui_logger.debug(">>> Result: \"{0}\"".format("DNS Management updated."))

        gui_logger.debug(">>> Ended tasks in \"dns_leak_switch_clicked\" thread.")

    def update_pvpn_plan(self, **kwargs):
        """Function that updates ProtonVPN plan.
        """
        gui_logger.debug(">>> Running \"set_protonvpn_tier\".")

        dialog_window = kwargs.get("dialog_window")
        #interface = kwargs.get("interface")
        protonvpn_plan = kwargs.get("tier")
        
        msg = "Unable to update ProtonVPN Plan!"
        if self.settings_service.set_pvpn_tier(protonvpn_plan):
            msg = "ProtonVPN Plan has been updated to <b>{}</b>!\nServers list will be refreshed.".format(kwargs.get("tier_display"))
        
        dialog_window.update_dialog(label=msg)

        gui_logger.debug(">>> Result: \"{0}\"".format("ProtonVPN Plan has been updated!"))

        # time.sleep(1.5)

        # populate_servers_dict = {
        #     "tree_object": interface.get_object("ServerTreeStore"),
        #     "servers": False
        # }

        #gobject.idle_add(populate_server_list, populate_servers_dict)

        gui_logger.debug(">>> Ended tasks in \"set_protonvpn_tier\" thread.")   

    def update_def_protocol(self, openvpn_protocol):
        """Function that updates default protocol.
        """
        gui_logger.debug(">>> Running \"set_default_protocol\".")

        if not self.settings_service.set_pvpn_tier(openvpn_protocol):
            gui_logger.debug(">>> Could not update default protocol.")   

        gui_logger.debug(">>> Ended tasks in \"set_default_protocol\" thread.")   

    def update_connect_preference(self, **kwargs):
        """Function that updates autoconnect. 
        """
        active_choice = kwargs.get("user_choice")
        dialog_window = kwargs.get("dialog_window")
        return_val = False

        gui_logger.debug(">>> Running \"update_connect_preference\".")

        if not "quick_connect" in kwargs:
            return_val = self.settings_service.set_autoconnect(active_choice)
        else:
            return_val = self.settings_service.set_quickconnect(active_choice)

        msg = "Unable to update configuration!"
        if return_val:
            msg = "{} setting updated to connect to <b>{}</b>!".format("Autoconnect" if not "quick_connect" in kwargs else "Quick connect", kwargs.get("country_display"))
        
        dialog_window.update_dialog(label=msg)

        gui_logger.debug(">>> Ended tasks in \"update_autoconnect\" thread.") 

    def update_killswitch(self, update_to):
        """Function that updates killswitch configurations. 
        """
        msg = "Unable to update killswitch configuration!"
        if self.settings_service.set_killswitch(update_to):
            msg = ">>> Kill Switch configuration updated to {}".format("enabled" if update_to == "1" else "disabled")

        gui_logger.debug(">>> Result: \"{0}\"".format(msg))

        gui_logger.debug(">>> Ended tasks in \"update_killswitch_switch_changed\" thread.")   

    def update_split_tunneling_status(self, update_to):
        if update_to == "1":
            result = "Split tunneling has been <b>enabled</b>!\n"
        else:
            result = "Split tunneling has been <b>disabled</b>!\n"

        if int(get_config_value("USER", "killswitch")):
            result = result + "Split Tunneling <b>can't</b> be used with Kill Switch, Kill Switch has been <b>disabled</b>!\n\n"
            time.sleep(1)

        msg = "Unable to update split tunneling status!"
        if not self.settings_service.set_split_tunneling(update_to):
            result = msg

        gui_logger.debug(">>> Result: \"{0}\"".format(result))

        gui_logger.debug(">>> Ended tasks in \"set_split_tunnel\" thread.") 

    def update_split_tunneling(self, **kwargs):
        """Function that updates split tunneling configurations.
        """
        gui_logger.debug(">>> Running \"set_split_tunnel\".")

        dialog_window = kwargs.get("dialog_window")
        split_tunneling_content = kwargs.get("split_tunneling_content")
        result = "Split tunneling configurations <b>updated</b>!\n"
        disabled_ks = False

        ip_list = self.settings_service.reformat_ip_list(split_tunneling_content)
        
        valid_ips = self.settings_service.check_valid_ips(ip_list)

        if len(valid_ips) > 1 and not valid_ips[0]:
            dialog_window.update_dialog(label="<b>{0}</b> is not valid!\nNone of the IP's were added, please try again with a different IP.".format(valid_ips[1]))
            gui_logger.debug("[!] Invalid IP \"{0}\".".format(valid_ips[1]))
            return

        if len(ip_list) == 0:
            result = "unable to disable Split Tunneling !\n\n"
            if self.settings_service.set_split_tunneling(0):
                result = "Split tunneling <b>disabled</b>!\n\n"
        else:
            result = result + "The following servers were added:\n\n{}".format([ip for ip in ip_list])
            
            if int(get_config_value("USER", "killswitch")):
                result = "Split Tunneling <b>can't</b> be used with Kill Switch.\nKill Switch could not be disabled, cancelling update!"
                if self.settings_service.set_killswitch(0):
                    result = result + "Split Tunneling <b>can't</b> be used with Kill Switch.\nKill Switch has been <b>disabled</b>!\n\n"
                    disabled_ks = True
    
            if not disabled_ks and not self.settings_service.set_split_tunneling_ips(ip_list):
                result = "Unable to add IPs to Split Tunneling file!"

        dialog_window.update_dialog(label=result)

        gui_logger.debug(">>> Result: \"{0}\"".format(result))

        gui_logger.debug(">>> Ended tasks in \"set_split_tunnel\" thread.")   

    def tray_configurations(self, **kwargs):
        """Function to update what the tray should display.
        """    
        setting_value = kwargs.get("setting_value")
        setting_display = kwargs.get("setting_display")
        gui_logger.debug(">>> Running \"tray_configurations\".")
        msg = ''

        if "serverload" in setting_display:
            msg = "server load"
        elif "server" in setting_display:
            msg = "server name"
        elif "data" in setting_display:
            msg = "data transmission"
        elif "time" in setting_display:
            msg = "time connected"

        result = "Tray {0} is <b>{1}</b>!".format(msg, "displayed" if setting_value == 1 else "hidden")
        if not self.settings_service.set_tray_setting(setting_display, setting_value):
            result = "Unable to update {} to {}!".format(msg, "displayed" if setting_value == 1 else "hidden")

        gui_logger.debug(">>> Result: \"{0}\"".format(result))

        gui_logger.debug(">>> Ended tasks in \"tray_configurations\" thread.")   
        
    def purge_configurations(self, dialog_window):
        """Function to purge all current configurations.
        """
        # To-do: Confirm prior to allowing user to do this
        gui_logger.debug(">>> Running \"set_split_tunnel\".")

        pvpn_disconnect(passed=True)

        if os.path.isdir(CONFIG_DIR):
            shutil.rmtree(CONFIG_DIR)
            gui_logger.debug(">>> Result: \"{0}\"".format("Configurations purged."))

        dialog_window.update_dialog(label="Configurations purged!")

        gui_logger.debug(">>> Ended tasks in \"set_split_tunnel\" thread.")   


    def load_configurations(self, object_dict):
        """Function that loads user configurations before showing the configurations window.
        """
        load_general_settings(object_dict["general"]["pvpn_plan_combobox"], object_dict["general"]["username"])
        load_tray_settings(object_dict["tray_comboboxes"])
        load_connection_settings(object_dict["connection"])
        load_advanced_settings(object_dict["advanced"])

    def load_general_settings(self, username, pvpn_plan_combobox):
        username = get_config_value("USER", "username")
        tier = int(get_config_value("USER", "tier"))

        # Populate username
        username.set_text(username)   
        # Set tier
        pvpn_plan_combobox.set_active(tier)

    def load_tray_settings(self, object_dict):
        # Load tray configurations
        for k,v in TRAY_CFG_DICT.items(): 
            setter = 0
            try: 
                setter = int(get_gui_config("tray_tab", v))
            except KeyError:
                gui_logger.debug("[!] Unable to find {} key.".format(v))

            combobox = object_dict[k]
            combobox.set_active(setter)

    def load_connection_settings(self, object_dict):
        # Set Autoconnect on boot combobox 
        autoconnect_liststore =  object_dict["autoconnect_liststore"]
        update_autoconnect_combobox = object_dict["update_autoconnect_combobox"]
        update_quick_connect_combobox = object_dict["update_quick_connect_combobox"]
        update_protocol_combobox = object_dict["update_protocol_combobox"]

        server_list = populate_autoconnect_list(autoconnect_liststore, return_list=True)

        #Get values
        try:
            autoconnect_setting = get_gui_config("conn_tab", "autoconnect")
        except (KeyError, IndexError):
            autoconnect_setting = 0
        try:
            quick_connect_setting = get_gui_config("conn_tab", "quick_connect")
        except (KeyError, IndexError):
            quick_connect = 0 
        default_protocol = get_config_value("USER", "default_protocol")

        # Get indexes
        autoconnect_index = list(server_list.keys()).index(autoconnect_setting)
        quick_connect_index = list(server_list.keys()).index(quick_connect_setting)

        # Set values
        update_autoconnect_combobox.set_active(autoconnect_index)
        update_quick_connect_combobox.set_active(quick_connect_index)

        if default_protocol == "tcp":
            update_protocol_combobox.set_active(0)
        else:
            update_protocol_combobox.set_active(1)

    def load_advanced_settings(self, object_dict):
        # User values
        dns_leak_protection = get_config_value("USER", "dns_leak_protection")
        custom_dns = get_config_value("USER", "custom_dns")
        killswitch = get_config_value("USER", "killswitch")

        try:
            split_tunnel = get_config_value("USER", "split_tunnel")
        except (KeyError, IndexError):
            split_tunnel = '0'

        # Object
        dns_leak_switch = object_dict["dns_leak_switch"]
        killswitch_switch = object_dict["killswitch_switch"]
        split_tunneling_switch = object_dict["split_tunneling_switch"]
        split_tunneling_list = object_dict["split_tunneling_list"]

        # Set DNS Protection
        if dns_leak_protection == '1':
        # if dns_leak_protection == '1' or (dns_leak_protection != '1' and custom_dns.lower() != "none"):
            dns_leak_switch.set_state(True)
        else:
            dns_leak_switch.set_state(False)

        # Populate Split Tunelling
        # Check if killswtich is != 0, if it is then disable split tunneling Function
        if killswitch != '0':
            killswitch_switch.set_state(True)
            split_tunneling_switch.set_property('sensitive', False)
        else:
            killswitch_switch.set_state(False)

        if split_tunnel != '0':
            split_tunneling_switch.set_state(True)
            killswitch_switch.set_property('sensitive', False)
            if killswitch != '0':
                split_tunneling_list.set_property('sensitive', False)
                object_dict["update_split_tunneling_button"].set_property('sensitive', False)
                
            split_tunneling_buffer = split_tunneling_list.get_buffer()
            content = ""
            try:
                with open(SPLIT_TUNNEL_FILE) as f:
                    lines = f.readlines()

                    for line in lines:
                        content = content + line

                    split_tunneling_buffer.set_text(content)
            except FileNotFoundError:
                split_tunneling_buffer.set_text(content)
        else:
            split_tunneling_switch.set_state(False)  

    def populate_autoconnect_list(self, autoconnect_liststore, return_list=False):
        """Function that populates autoconnect dropdown list.
        """
        autoconnect_alternatives = self.settings_service.generate_autoconnect_list()
        other_choice_dict = {
            "dis": "Disabled",
            "fast": "Fastest",
            "rand": "Random", 
            "p2p": "Peer2Peer", 
            "sc": "Secure Core (Plus/Visionary)",
            "tor": "Tor (Plus/Visionary)"
        }
        return_values = collections.OrderedDict()

        for alt in autoconnect_alternatives:
            if alt in other_choice_dict:
                # if return_list:
                return_values[alt] = other_choice_dict[alt]
                # else:
                autoconnect_liststore.append([alt, other_choice_dict[alt], alt])
            else:
                for k,v in country_codes.items():
                    if alt.lower() == v.lower():
                        # if return_list:
                        return_values[k] = v
                        # else:
                        autoconnect_liststore.append([k, v, k])
        
        if return_list:
            return return_values
