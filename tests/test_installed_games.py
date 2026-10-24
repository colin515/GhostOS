from pathlib import Path
import pytest
import vdf
from agent.installed_games import installed_games
from agent.app_resolution import resolve_installed
from agent.navigation import Navigation


def test_installed_steam_library_is_discovered_without_guessing_executable_paths(tmp_path):
    steam,library = tmp_path/'steam',tmp_path/'other-library'
    (steam/'steamapps').mkdir(parents=True)
    (library/'steamapps/common/Portal 2').mkdir(parents=True)
    (steam/'steamapps/libraryfolders.vdf').write_text(vdf.dumps({'libraryfolders':{'0':{'path':str(steam)},'1':{'path':str(library)}}}))
    (library/'steamapps/appmanifest_620.acf').write_text(vdf.dumps({'AppState':{'appid':'620','name':'Portal 2','installdir':'Portal 2'}}))
    result = installed_games([steam])
    assert result['Portal 2'].app_id == '620'
    assert result['Portal 2'].directory == library/'steamapps/common/Portal 2'
    # A manifest cannot smuggle a URI or filesystem traversal into launch resolution.
    (library/'steamapps/appmanifest_42.acf').write_text(vdf.dumps({'AppState':{'appid':'42','name':'Bad','installdir':'../outside'}}))
    assert 'Bad' not in installed_games([steam])


def test_common_game_alias_and_typo_use_inventory_and_do_not_select_studio():
    names = ['Minecraft Launcher','Roblox Studio','Roblox Player']
    assert resolve_installed('Minecraft',names) == 'Minecraft Launcher'
    assert resolve_installed('Minecrfat',names) == 'Minecraft Launcher'
    assert resolve_installed('Roblox',names) == 'Roblox Player'
    with pytest.raises(FileNotFoundError):
        resolve_installed('Portal 2',['Portal 1'])
    with pytest.raises(FileNotFoundError):
        resolve_installed('Unreal',['Unreal Editor','Unreal Engine'])


@pytest.mark.parametrize('name',['ChatGPT','Chat GPT','ChatGBT'])
def test_chatgpt_always_uses_the_canonical_site(name):
    request = Navigation.parse('Please open ' + name)
    assert request.simple
    assert request.next_action().args['url'] == 'https://chatgpt.com/'


def test_named_game_launch_is_a_native_prerequisite_even_in_game_mode():
    request = Navigation.parse('Open the game Portal 2',game_mode=True)
    assert request.simple and request.app == 'Portal 2'
    assert request.next_action().kind == 'ensure_app'


def test_model_domain_typo_is_corrected_but_explicit_user_urls_are_preserved():
    from agent.navigation import canonical_destination
    assert canonical_destination('Open ChatGPT','https://chatgbt.com/') == 'https://chatgpt.com/'
    assert canonical_destination('Open https://chatgbt.com/','https://chatgbt.com/') == 'https://chatgbt.com/'
