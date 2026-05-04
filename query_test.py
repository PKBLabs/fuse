from db_utils import (
    get_all_elements,
    get_all_components_for_element,
    get_component_details,
)

print(get_all_elements()[:5])

opal_components = get_all_components_for_element("Opal")
print(opal_components)

if opal_components:
    component_id = opal_components[0]["id"]
    details = get_component_details(component_id)
    print(details)