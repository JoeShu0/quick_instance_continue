'''

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

'''

bl_info = {
    "name": "Quick Instances (Groups)",
    "author": "Michael Soluyanov (crantisz@gmail.com, multlabs.com)",
    "version": (0, 3, 4),
    "blender": (4, 1, 0),
    "location": "Viewport: Ctrl + G, Gtrl + Shift + G, Gtrl + Alt + G, Tab",
    "description": "Create a library instance and replace selected objects by them",
    "warning": "",
    "category": "Object"
}

from bpy.types import (
    Panel
)
import math 
import copy
import bpy
import mathutils
from .utils.registration import get_keys, register_keymaps, unregister_keymaps
import rna_keymap_ui

def flatten(mat):
    dim = len(mat)
    return [mat[j][i] for i in range(dim)
            for j in range(dim)]


class qInstanceSceneSetting(bpy.types.PropertyGroup):
    dist: bpy.props.FloatProperty(name="Saved Camera distance")
    view: bpy.props.FloatVectorProperty(
        name="Saved Camera Matrix",
        size=16,
        subtype="MATRIX")
    scene: bpy.props.PointerProperty(name="Saved Scene return to", type=bpy.types.Scene)
    local: bpy.props.BoolProperty(name="Saved local State")
    persp: bpy.props.BoolProperty(name="Saved Perspective State")

    world: bpy.props.BoolProperty(name="Saved hdri State")
    world_render: bpy.props.BoolProperty(name="Saved world hdri render State")


def editLibraryInstance(s, context, skiptesting):
    rv3d = context.space_data.region_3d

    # return back from collection
    if context.scene.name == "Library" and (len(context.selected_objects) == 0 or skiptesting):
        rv3d.view_distance = context.scene.qInstanceProps.dist
        rv3d.is_perspective = context.scene.qInstanceProps.persp
        rv3d.view_matrix = context.scene.qInstanceProps.view
        if bpy.app.version>(2,81,11):
            context.space_data.shading.use_scene_world_render = context.scene.qInstanceProps.world_render
        context.space_data.shading.use_scene_world = context.scene.qInstanceProps.world
        context.window.scene = context.scene.qInstanceProps.scene

        return True

    library = bpy.data.scenes["Library"]

    # save collection reference to return to
    if context.window.scene.name != "Library":
        library.qInstanceProps.scene = context.window.scene
        library.qInstanceProps.view = flatten(rv3d.view_matrix)
        library.qInstanceProps.dist = rv3d.view_distance
        library.qInstanceProps.persp = rv3d.is_perspective
        library.qInstanceProps.world = context.space_data.shading.use_scene_world
        if bpy.app.version>(2,81,11):
            library.qInstanceProps.world_render = context.space_data.shading.use_scene_world_render

    context.space_data.shading.use_scene_world = False
    if bpy.app.version>(2,81,11):
        context.space_data.shading.use_scene_world_render = False

    # return from local view
    space_data = context.space_data
    if space_data.type == 'VIEW_3D':
        if space_data.local_view:
            bpy.ops.view3d.localview()

    if context.active_object.instance_collection is None:
        s.report({'ERROR'}, "Selected object doesn't instance a collection")
        return False
    
    collection = context.active_object.instance_collection 
    libname = context.active_object.instance_collection.name

    if libname not in library.collection.children.keys():
        s.report({'ERROR'}, "Instance of collettion '%s' doesn't located in scene 'Library'" % libname)
        return False

    context.window.scene = library
    for lc in context.view_layer.layer_collection.children:
        lc.exclude = lc.name != libname
        if lc.name == libname:
            context.view_layer.active_layer_collection = lc
        
    

    bpy.ops.view3d.view_all()
    bpy.ops.object.select_all(action='DESELECT')


def createLibraryScene(context):
    if "Library" not in bpy.data.scenes.keys():
        currentScene = bpy.context.scene
        bpy.ops.scene.new(type='NEW')
        context.scene.name = "Library"
        context.window.scene = currentScene


def createLibraryInstance(context, instname, instance_center):
    # create a scene Library, if it doesn't exisists
    createLibraryScene(context)

    library = bpy.data.scenes['Library']

    # Create a collection with given name
    collection = bpy.data.collections.new(name=instname)
    library.collection.children.link(collection)

    # find center of collection
    collection_loc = mathutils.Vector((0, 0, 0))

    if instance_center == 'ACTIVE':
        collection_loc += context.active_object.matrix_world.translation

    if instance_center == 'CURSOR':
        collection_loc = context.scene.cursor.location

    if instance_center == 'MEDIAN':
        for obj in context.selected_objects:
            collection_loc += obj.matrix_world.translation
        collection_loc = collection_loc / len(context.selected_objects)
        
    if(context.scene == library):    
        context.view_layer.layer_collection.children[collection.name].exclude=True
    
    # set ne location for root objects
    for obj in context.selected_objects:
        
        if obj.parent not in context.selected_objects:
            obj.parent = None
            current_loc = obj.matrix_world.translation
            obj.matrix_world.translation = current_loc - collection_loc
        print(obj.parent not in context.selected_objects)
        
    # move object to new collection    
    for obj in context.selected_objects:   
        collection.objects.link(obj)
        for col in obj.users_collection:
            if col!=collection:
                col.objects.unlink(obj)
        
    # replace objects by collection        
    #bpy.ops.object.delete( use_global=False)
     
    
    bpy.ops.object.collection_instance_add(collection=collection.name, align="WORLD", location=collection_loc)


def ungroupLibraryInstance(s, context, removefromlib):
    objs = bpy.data.objects
    listremove_collections = []

    createLibraryScene(context)
    
    library = bpy.data.scenes["Library"]

    listremove_objects = getLibraryInstances(context.selected_objects, False)

    if len(listremove_objects) == 0:
        s.report({'ERROR'}, "Selected objects is not instances or instances are not from Library scene")
        return False;

    for obj in listremove_objects:
        if len(obj.instance_collection.users_dupli_group) <= 1:
            listremove_collections.append(obj.instance_collection)

    #bpy.ops.object.duplicates_make_real(
        #{'selected_objects': listremove_objects, 'active_object': listremove_objects[0]})
    
    bpy.ops.object.duplicates_make_real()

    for obj in listremove_objects:
        objs.remove(obj)

    if removefromlib:
        cols = bpy.data.collections
        for col in listremove_collections:
            cols.remove(col)


def getLibraryInstances(objects, skiplibrarycheck):
    list_objects = []
    
    for obj in objects:
        if obj.type != 'EMPTY':
            continue
        if obj.instance_collection is None:
            continue
        if obj.instance_type != 'COLLECTION':
            continue
        if skiplibrarycheck:
            list_objects.append(obj)
            continue
        if "Library" not in bpy.data.scenes.keys():
            continue
        library = bpy.data.scenes["Library"]
        if obj.instance_collection.name not in library.collection.children:
            continue
        if library.collection.children[obj.instance_collection.name] != obj.instance_collection:
            continue
        list_objects.append(obj)

    return list_objects


def makeSingleUserLibraryInstance(s, context, objectstype):
    library = bpy.data.scenes["Library"]
    list_objects = getLibraryInstances(context.selected_objects, False)

    if len(list_objects) == 0:
        s.report({'ERROR'}, "Selected objects is not instances or instances are not from Library scene")
        return False;

    for empty in list_objects:
        oldcol = empty.instance_collection
        newcol = bpy.data.collections.new(name=empty.instance_collection.name)
        library.collection.children.link(newcol)

        for obj in oldcol.objects:
            if objectstype == 'LINK':
                newobj = obj.copy()
            else:
                newobj = obj.copy()
                if not newobj.data is None:
                    newobj.data = newobj.data.copy()
            newcol.objects.link(newobj)

        empty.instance_collection = newcol

    return True

def addToLibraryInstance(context):
    
    colobj = getLibraryInstances([context.active_object], False)
    
    if len(colobj)==0:
        return False
    
    colobj=colobj[0]
    collection = colobj.instance_collection
    
    remove_list = []
    
    for obj in context.selected_objects:
        if obj == colobj:
            continue 
        
        remove_list.append(obj)
        collection.objects.link(obj)
        obj.parent = None
        obj.matrix_world=   mathutils.Matrix.Translation(collection.instance_offset) @ colobj.matrix_world.inverted_safe() @  obj.matrix_world 
        
    bpy.ops.object.delete(
        {'selected_objects': remove_list, 'active_object': remove_list[0]})
 
 
def removeFromLibraryInstance(context, object):
    
    colobj=context.active_object
    collection = colobj.instance_collection
    
    obj = collection.objects[object]
    
    context.collection.objects.link(obj)
    
    
    
    obj.parent = None
    
    obj.matrix_world = colobj.matrix_world @ mathutils.Matrix.Translation(-collection.instance_offset) @ obj.matrix_world 
    
    
    
    bpy.ops.object.delete(
        {'scene': bpy.data.scenes["Library"], 'selected_objects': [obj], 'active_object': obj})    
    
    return 
    
    
def MoveCollectionToLibrary(context):
    
    createLibraryScene(context)
    library = bpy.data.scenes["Library"]

    list_objects = getLibraryInstances(context.selected_objects, True)

    for empty in list_objects:
        col = empty.instance_collection

        if col.name not in library.collection.children:
            library.collection.children.link(col)







class OBJECT_OT_addSelectedToCollection(bpy.types.Operator):
    """Add selected objects to a collection of active Library Instance"""
    bl_idname = "object.add_to_library_instance"
    bl_label = "Add selected to Library Instance"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if len(context.selected_objects) <= 1:
            return False
        objects = getLibraryInstances([context.active_object], False)
        if len(objects) == 0:
            return False
        return True

    def execute(self, context):
        addToLibraryInstance(context)
        return {'FINISHED'}

def objectInCollection(self, context):
    
    colobj=context.active_object
    collection = colobj.instance_collection  
    return [(obj.name, obj.name, '') for obj in collection.objects]


class OBJECT_OT_removeFromCollection(bpy.types.Operator):
    """Add selected objects to a collection of active Library Instance"""
    bl_idname = "object.remove_from_library_instance"
    bl_label = "Remove an object from Library Instance"
    bl_options = {'REGISTER', 'UNDO'}
    bl_property = 'objectlist'
    
    objectlist : bpy.props.EnumProperty(items = objectInCollection) 

    @classmethod
    def poll(cls, context):
        objects = getLibraryInstances([context.active_object], False)
        if len(objects) == 0:
            return False
        return True
    
    def execute(self, context):
        removeFromLibraryInstance(context, self.objectlist)
        return {'FINISHED'}
    
    def invoke(self, context, event):
        wm = context.window_manager
        wm.invoke_search_popup(self)
        return {'RUNNING_MODAL'}    




class OBJECT_OT_LibraryInstance(bpy.types.Operator):
    """Create a collection with selected objects in Library"""
    bl_idname = "object.library_instance"
    bl_label = "Convert to Library Group"
    bl_options = {'REGISTER', 'UNDO'}

    instname: bpy.props.StringProperty(name="Instance Name", default="Group")
    instance_center: bpy.props.EnumProperty(
        name='Center of Instance',
        items={
            ('WORLD', 'World', 'Center of world coordinates'),
            ('MEDIAN', 'Median Point', 'Median of object origins'),
            # ('BOX', 'Bounding Box Center', 'Center of bounding box'),
            ('CURSOR', '3D Cursor', '3D cursor coordinates'),
            ('ACTIVE', 'Active Object', 'Active object orign')},
        default='MEDIAN')

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def execute(self, context):
        createLibraryInstance(context, self.instname, self.instance_center)
        return {'FINISHED'}


class OBJECT_OT_makeSingleUserLibraryInstance(bpy.types.Operator):
    """Make instanced collection single user"""
    bl_idname = "object.make_single_user_library_instance"
    bl_label = "Edit Instanced Collection (Back on nothing selected)"
    bl_options = {'REGISTER', 'UNDO'}

    objects: bpy.props.EnumProperty(
        name='Link or copy objects',
        items={
            ('LINK', 'Link', 'Link objects'),
            ('COPY', 'Copy', 'Make full copy of group')},

        default='COPY')

    @classmethod
    def poll(cls, context):
        if "Library" not in bpy.data.scenes.keys():
            return False
        return len(context.selected_objects) > 0

    def execute(self, context):
        makeSingleUserLibraryInstance(self, context, self.objects)
        return {'FINISHED'}


class OBJECT_OT_EditLibraryInstanceSkipTesting(bpy.types.Operator):
    """Edit instanced collection in Library and back even if something selected"""
    bl_idname = "object.edit_library_instance_skip_testing"
    bl_label = "Edit Instanced Collection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if "Library" not in bpy.data.scenes.keys():
            return False
        if context.scene.name == "Library":
            return True
        if context.active_object == None:
            return False
        if context.active_object.type != 'EMPTY':
            return False
        return True

    def execute(self, context):
        editLibraryInstance(self, context, True)
        return {'FINISHED'}


class OBJECT_OT_EditLibraryInstance(bpy.types.Operator):
    """Edit instanced collection in Library"""
    bl_idname = "object.edit_library_instance"
    bl_label = "Edit Instanced Collection (Tab-compatible)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(self, context):
        if "Library" not in bpy.data.scenes.keys():
            return False
        if context.scene.name == "Library" and (len(context.selected_objects) == 0):
            return True
        if context.active_object == None:
            return False
        if context.active_object.type != 'EMPTY':
            return False
        return True

    def execute(self, context):
        editLibraryInstance(self, context, False)
        return {'FINISHED'}


class OBJECT_OT_MoveCollectionToLibrary(bpy.types.Operator):
    """Move collection to Library Scene"""
    bl_idname = "object.add_collection_to_library"
    bl_label = "Move Collection to Library "
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def execute(self, context):
        MoveCollectionToLibrary(context)
        return {'FINISHED'}


class OBJECT_OT_ungroupLibraryInstance(bpy.types.Operator):
    """Ungroup instanced collection and remove it from Library"""
    bl_idname = "object.library_instance_ungroup"
    bl_label = "Ungroup Instanced Collection"
    bl_options = {'REGISTER', 'UNDO'}

    removefromlib: bpy.props.BoolProperty(name="Remove from Library Scene", default=True)

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) > 0

    def execute(self, context):
        ungroupLibraryInstance(self, context, self.removefromlib)
        return {'FINISHED'}


class VIEW3D_PT_library_instance_menu(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_label = "Quick instance menu"
    bl_idname = "VIEW3D_PT_library_instance_menu"

    def draw(self, context):

        layout = self.layout

        layout.label(text="Quick instance menu")

        if context.scene.name == "Library":
            layout.operator("object.edit_library_instance_skip_testing", text="Back to working Scene",
                            icon='SCREEN_BACK')

        if len(context.selected_objects) == 0:
            layout.label(text="Nothing selected")
            return

        if context.object.instance_type == 'COLLECTION':
            layout.prop(context.object, "instance_collection", text="Collection")
          
        if len(getLibraryInstances([context.active_object], False)) > 0:
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("object.remove_from_library_instance",  text="Remove object from Instance", icon='REMOVE', )   
            
        if len(context.selected_objects) > 1:
            if len(getLibraryInstances([context.active_object], False)) > 0:
                layout.operator("object.add_to_library_instance", text="Add selected to Instance", icon='ADD')

        layout.operator("object.library_instance", text="Group objects", icon='ADD')

        layout.separator()

        objects = getLibraryInstances(context.selected_objects, False)

        if (len(objects) == 0):
            layout.label(text="Selected objects is not instances")
            layout.label(text="or instances are not from Library scene")

            objects = getLibraryInstances(context.selected_objects, True)
            if (len(objects) > 0):
                layout.operator("object.add_collection_to_library", text="Fix this", icon='LINKED')

            return

        layout.operator("object.edit_library_instance", text="Edit Instance", icon='OBJECT_DATAMODE')

        layout.label(text="Make single user with")
        layout.operator("object.make_single_user_library_instance", text="Linked objects",
                        icon='LINKED').objects = 'LINK'
        layout.operator("object.make_single_user_library_instance", text="Copied objects",
                        icon='DUPLICATE').objects = 'COPY'

        layout.separator()

        layout.label(text="Ungroup Library Instances")
        layout.operator("object.library_instance_ungroup", text="And remove it from Library", icon='REMOVE')
        layout.operator("object.library_instance_ungroup", text="And Keep it in Library",
                        icon='REMOVE').removefromlib = False




class qInstance_PT_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    
    def draw(self, context):
        layout = self.layout
       
        
        wm = bpy.context.window_manager
        kc = wm.keyconfigs.addon
        
        keylist = get_keys()
        
        for idx, item in enumerate(keylist[0]):
            keymap = item.get("keymap")
            if not keymap:
                continue
            
            km = kc.keymaps.get(keymap)
            kmi = None
            
            if km:
                idname = item.get("idname")

                for kmitem in km.keymap_items:
                    if kmitem.idname != idname:
                        continue
                    
                    properties = item.get("properties")

                    if properties:
                        if all([getattr(kmitem.properties, name, None) == value for name, value in properties]):
                            kmi = kmitem
                            break
                    else:
                        kmi = kmitem
                        break

            if kmi:
                row=layout.row() 
                rna_keymap_ui.draw_kmi(["ADDON", "USER", "DEFAULT"], kc, km, kmi, row, 0)

                drawn = True
                
                    
                    

def draw(self, context):
    layout = self.layout
    layout.label(text='Add bevel modifier:')
    row = layout.row()
    row.prop(self, 'add_bevel', expand=True)

classes = {
    OBJECT_OT_LibraryInstance,
    OBJECT_OT_EditLibraryInstanceSkipTesting,
    OBJECT_OT_EditLibraryInstance,
    OBJECT_OT_ungroupLibraryInstance,
    OBJECT_OT_makeSingleUserLibraryInstance,
    OBJECT_OT_MoveCollectionToLibrary,
    OBJECT_OT_addSelectedToCollection,
    OBJECT_OT_removeFromCollection,
    qInstanceSceneSetting,
    qInstance_PT_Preferences,
    VIEW3D_PT_library_instance_menu
}


def register():
    global keymaps
    for cls in classes:
        bpy.utils.register_class(cls)
    keys = get_keys()
    keymaps = register_keymaps(keys)
    bpy.types.Scene.qInstanceProps = bpy.props.PointerProperty(type=qInstanceSceneSetting)


def unregister():
    global keymaps
    unregister_keymaps(keymaps)
    for cls in classes:
        print(cls)
        bpy.utils.unregister_class(cls)



if __name__ == "__main__":
    register()
