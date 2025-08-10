class B:    
    def __init__(self):
        self.name = "B"

    def method(self):
        return "Method of B"

class A:
    def __init__(self):
        self.name = "A"
        self.B = B()

    def method(self):
        return "Method of A"
    
a = A()
print(getattr(a, 'B').method())  # Accessing B's method through A
print(getattr(a, 'B.name'))  # Accessing B's name through A