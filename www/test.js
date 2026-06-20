var x = 2
x + x

console.log("Hi from JS!")

function lengthCheck() {
    var name = this.getAttribute("name")
    var value = this.getAttribute("value")
    if (value.length > 100) {
        console.log("Input " + name + " has too much text.")
    }
}

inputs = document.querySelectorAll('input')
for (var i = 0; i < inputs.length; i++) {
    inputs[i].addEventListener("keydown", lengthCheck);
}
