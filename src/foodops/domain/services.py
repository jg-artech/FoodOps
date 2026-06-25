"""Servicios de negocio"""

class OrdenService:
    """Servicio para operaciones de órdenes"""
    
    def __init__(self):
        self.ordenes = {}
    
    def crear_orden(self, numero: str, punto_id: int):
        """Crea una nueva orden"""
        orden = {
            "numero": numero,
            "punto_id": punto_id,
            "estado": "pendiente",
            "items": []
        }
        self.ordenes[numero] = orden
        return orden
    
    def obtener_orden(self, numero: str):
        """Obtiene una orden por número"""
        return self.ordenes.get(numero)

class InventarioService:
    """Servicio para inventario de ingredientes"""
    
    def __init__(self):
        self.ingredientes = {}
    
    def obtener_stock(self, ingrediente_id: int):
        """Obtiene stock de ingrediente"""
        return self.ingredientes.get(ingrediente_id)
